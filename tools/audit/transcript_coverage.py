#!/usr/bin/env python3
"""Check that every sentence the owner typed in a session appears in the records.

Mechanical and reproducible: no randomness, no model calls, sorted outputs.
It reads the session JSONL, keeps only the owner's own messages, splits them into
sentences, and looks for each sentence of 4+ words in the record files:
  EXACT  the normalized sentence is a substring of a normalized record file
  NEAR   a record window holds >= 60% of the sentence's distinct word 3-grams
  NONE   neither
Judgment starts where this script stops: a NONE or a low NEAR still needs a reader.

Example:
  python3 tools/audit/transcript_coverage.py \
      --until 2026-10-01T06:00:00Z \
      --tsv docs/refactor/audit-transcript-2026-10-01-coverage.tsv
"""
import argparse
import bisect
import collections
import glob
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLAUDE_DIR = "/root/.claude/projects/-root-groundstation"
DEFAULT_JSONL = CLAUDE_DIR + "/1d8b196b-7abe-45b9-a9d6-ddf7daef5fae.jsonl"
MEMORY_DIR = CLAUDE_DIR + "/memory"
RECORDS = [
	"docs/task-active-harden2-handoff-2026-10-01.md",
	"docs/harden2-status.md",
	"docs/spec-harden2-cleanup.md",
	"docs/guidelines.md",
	"docs/task-active-harden2-refactor-handoff.md",
	"docs/HISTORY.md",
	"CLAUDE.md",
]
MIN_WORDS = 4
NEAR_SHARE = 0.6
# Harness frames, not owner text. A message that starts with one is dropped.
DROP_PREFIXES = [
	"[Subagent hand-back]",
	"<task-notification>",
	"<agent-message",
	"<local-command",
	"Caveat: The messages below",
	"This session is being continued from a previous conversation",
	"<command-name>",
	"[Request interrupted by user",
]
# These frames never come from the owner's keyboard, wherever they sit.
DROP_ANYWHERE = [
	"[Subagent hand-back]",
	"<task-notification>",
	"<agent-message",
]
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
IDE_TAG = re.compile(r"<ide_(\w+)>.*?</ide_\1>", re.S)
QUOTE_MARKS = re.compile("['\"`‘’“”]")
NOT_WORD = re.compile(r"[^\w\s]")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def normalize(text):
	lowered = text.lower()
	unquoted = QUOTE_MARKS.sub("", lowered)
	spaced = NOT_WORD.sub(" ", unquoted)
	return " ".join(spaced.split())


def block_text(content):
	# A user entry holds a plain string, or blocks; tool results are not owner text.
	if isinstance(content, str):
		return content
	texts = []
	for block in content:
		if not isinstance(block, dict):
			continue
		if block.get("type") != "text":
			continue
		texts.append(block.get("text", ""))
	return "\n".join(texts)


def owner_text(entry):
	# Returns (key, timestamp, raw text) for an owner message, else None.
	kind = entry.get("type")
	if kind == "user":
		if entry.get("isMeta") or entry.get("isSidechain"):
			return None
		raw = block_text(entry.get("message", {}).get("content", ""))
		return (entry.get("uuid"), entry.get("timestamp"), raw)
	if kind != "attachment":
		return None
	# A message typed while the agent works arrives as a queued command.
	attachment = entry.get("attachment", {})
	if attachment.get("type") != "queued_command":
		return None
	if (attachment.get("origin") or {}).get("kind") != "human":
		return None
	stamp = attachment.get("timestamp") or entry.get("timestamp")
	raw = block_text(attachment.get("prompt", ""))
	return (attachment.get("source_uuid"), stamp, raw)


def drop_reason(text):
	if not text:
		return "no text (tool results only)"
	for prefix in DROP_PREFIXES:
		if text.startswith(prefix):
			return prefix
	for marker in DROP_ANYWHERE:
		if marker in text:
			return marker
	return None


def load_messages(jsonl, until):
	seen_keys = set()
	seen_texts = set()
	kept = []
	dropped = collections.Counter()
	with open(jsonl, encoding="utf-8") as source:
		for line in source:
			# The live session may be mid-write: skip a partial last line.
			if not line.endswith("\n"):
				continue
			found = owner_text(json.loads(line))
			if found is None:
				continue
			key, stamp, raw = found
			if key in seen_keys:
				continue
			seen_keys.add(key)
			if until and stamp > until:
				continue
			text = IDE_TAG.sub("", SYSTEM_REMINDER.sub("", raw)).strip()
			reason = drop_reason(text)
			if reason:
				dropped[reason] += 1
				continue
			if text in seen_texts:
				continue
			seen_texts.add(text)
			kept.append((stamp, text))
	kept.sort()
	return kept, dropped


class Corpus:
	def __init__(self, paths):
		self.mk_names = []
		self.mk_joined = []
		self.mk_lines = []
		self.mk_index = collections.defaultdict(list)
		for path in paths:
			self._add(path)
		return

	def _add(self, path):
		file_id = len(self.mk_names)
		words = []
		lines = []
		with open(path, encoding="utf-8") as source:
			for number, line in enumerate(source, 1):
				line_words = normalize(line).split()
				words.extend(line_words)
				lines.extend([number] * len(line_words))
		name = os.path.relpath(path, REPO)
		if path.startswith(MEMORY_DIR):
			name = "memory/" + os.path.basename(path)
		self.mk_names.append(name)
		self.mk_joined.append(" " + " ".join(words) + " ")
		self.mk_lines.append(lines)
		for pos in range(len(words) - 2):
			self.mk_index[tuple(words[pos:pos + 3])].append((file_id, pos))
		return

	def where(self, file_id, word_pos):
		lines = self.mk_lines[file_id]
		return "%s:%d" % (self.mk_names[file_id], lines[min(word_pos, len(lines) - 1)])

	def exact(self, sentence):
		needle = " " + sentence + " "
		for file_id, joined in enumerate(self.mk_joined):
			offset = joined.find(needle)
			if offset < 0:
				continue
			return self.where(file_id, joined.count(" ", 0, offset))
		return None

	def near(self, words):
		grams = sorted(set(tuple(words[i:i + 3]) for i in range(len(words) - 2)))
		hits = collections.defaultdict(list)
		for gram_id, gram in enumerate(grams):
			for file_id, pos in self.mk_index.get(gram, []):
				hits[file_id].append((pos, gram_id))
		width = 2 * len(words)
		best = (0, -1, 0)
		for file_id in sorted(hits):
			found = sorted(hits[file_id])
			starts = [pos for pos, _ in found]
			for left, (pos, _) in enumerate(found):
				right = bisect.bisect_right(starts, pos + width)
				share = len(set(gram for _, gram in found[left:right]))
				if share > best[0]:
					best = (share, file_id, pos)
		if best[1] < 0:
			return (0.0, "")
		return (best[0] / len(grams), self.where(best[1], best[2]))


def classify(corpus, sentence):
	words = sentence.split()
	location = corpus.exact(sentence)
	if location:
		return ("EXACT", 1.0, location)
	score, location = corpus.near(words)
	if score >= NEAR_SHARE:
		return ("NEAR", score, location)
	return ("NONE", score, location)


def record_paths():
	paths = [os.path.join(REPO, name) for name in RECORDS]
	paths.extend(sorted(glob.glob(MEMORY_DIR + "/*.md")))
	return paths


def write_messages(path, messages):
	with open(path, "w", encoding="utf-8") as out:
		for number, (stamp, text) in enumerate(messages, 1):
			out.write("\n## MSG %d | %s\n\n%s\n" % (number, stamp, text))
	return


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--jsonl", default=DEFAULT_JSONL)
	parser.add_argument("--until", default="", help="last timestamp to read (ISO)")
	parser.add_argument("--tsv", required=True)
	parser.add_argument("--messages", default="", help="also write the owner messages")
	args = parser.parse_args()
	messages, dropped = load_messages(args.jsonl, args.until)
	if args.messages:
		write_messages(args.messages, messages)
	corpus = Corpus(record_paths())
	counts = collections.Counter()
	with open(args.tsv, "w", encoding="utf-8") as out:
		out.write("msg\ttimestamp\tsent\tclass\tscore\twhere\tsentence\n")
		for number, (stamp, text) in enumerate(messages, 1):
			pieces = [p.strip() for p in SENTENCE_END.split(text) if p.strip()]
			for index, piece in enumerate(pieces, 1):
				sentence = normalize(piece)
				if len(sentence.split()) < MIN_WORDS:
					counts["SHORT"] += 1
					continue
				kind, score, location = classify(corpus, sentence)
				counts[kind] += 1
				flat = " ".join(piece.split())
				row = (number, stamp, index, kind, score, location, flat)
				out.write("%d\t%s\t%d\t%s\t%.2f\t%s\t%s\n" % row)
	print("owner messages: %d" % len(messages))
	if messages:
		print("range: %s .. %s" % (messages[0][0], messages[-1][0]))
	for reason in sorted(dropped):
		print("dropped %r: %d" % (reason, dropped[reason]))
	for kind in sorted(counts):
		print("%s: %d" % (kind, counts[kind]))
	return


if __name__ == "__main__":
	main()
