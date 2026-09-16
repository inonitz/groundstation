# Scheduled — fuse harden2 into llm_to_action

Runs AFTER the freeze. The C++ llm_to_action engine is the destination product; harden2 is the
proven Hebrew voice + guard + SAM3 layer.

Task: assess whether to fold harden2's layer onto the llm_to_action C++ engine now, or whether more
is needed first. Scope it as its own tasks-active folder when reached; perception -> C++ for embedded.
Done when: the fusion path is decided and, if taken, harden2's layer runs on the llm_to_action engine.
