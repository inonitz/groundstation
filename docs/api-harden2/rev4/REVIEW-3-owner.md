# The owner's review, round 3 (2026-10-02), word for word (of the rev4 headers after the layout, HDR4)

Another review -
1. Audio.h -
* What is the point of AsrServerProcess? what is it launching? What does the process actually do?
* How Does the phoneBridge know on what IP to listen? How does it interface with AsrServerProcess?
* split to audio_in.h and audio_out.h

* What happens if we need to streamline a sentence both from the phone AND the laptop? How would speechOut handle it? It seems that both requests would be placed on the worker thread, won't they stall each other?

2. dji_app.h -
* Why does it still take a handle to perf if it isn't using perf in the struct? I don't understand.
* What is the point of DjiMockProcess actually?
*  API Looks good besides that.
* Is the handling of commands to the DJIAPI handled by the the flight controller now? Seems like it. When manual=true are commands being dropped into a sink?

3. flight.h -
* Bad naming, Why is it called Flight? What the fuck is that naming? Couldn't you atleast talk to me before using this stupid name?
* What is it called "FlightFly"? This is so generic and it doesn't say anything about actual intent! CLAUDE! FUCK SAKE! IT SHOULD BE CALLED WHAT IT ACTUALLY IS! SENDING A JSON BUFFER OF COMMANDS! IT SHOULD EXPLAIN THAT AT THE MINIMUM!
* FlightHalt is also fucking bad naming - WHY DO YOU NEED AN EXPLANTION AT THE TOP WHEN THE WHOLE INTENT COULD BE INSIDE THE FUNCTION NAME INSTEAD???
* Same thing about FlightSetManual - WHAT DOES MANUAL MEAN???? ONLY YOU AND I KNOW WHAT IT MEANS! NO ONE ELSE! ITS NOT FUCKING CLEAR!
* [API Wide Command] - Do A style check for intent-based naming for the whole API.
* Why do we own SessionLog? Do we own a handle to it? How do we actually use SessionLog In practice here?

4. frames.h -
* You hold 32 frames in flight, but the memory for the frames is allocated elsewhere. Where? In one shared memory region? Scattered? What is the source of the frame?
* Who is actually responsible for initialization of the frame buffer? The memory is shared between processes, who actually has the responsibility for initialization and destruction? Between who is the memory shared between/with?
* How do the processes/services in question interface with the ringbuffer? I need a proper answer here, Pin/unpin is not clear enough.
* Who is to say that 32 frames is enough? Doesn't the app run ~ 15-30 fps from the camera? That captures only a second of data at most! Do you really think we would be able to save the vision-task data to disk when we have such a small time to shuffle between frames? What the hell are you thinking exactly here claude?
* Besides these, I have no problem with the implementation, its literally a standard interface to a ringbuffer, specialized specifically for a "frame"

5. gemma.h -
* How detached are you from reality? Do you actually know how to start the gemma llama-server? Do you know what is required and what is not required for it? That information that you find, is the exact information needed here. Some of it is already in the config/* folder, the internal machinations are not.
* Besides that, looks good. I just don't understand how you plan to terminate the gemma process.

6. keys.h - Good
7. log.h -
* what is the point of TurnInput@seq?
* What is TurnInput@epoch?
* Turn Struct looks good
* How do you plan to replay a whole session when you don't store data about images, including bboxes and the full noun/word-list used with SAM3? It seems to me like VisionJob doesn't hold all of the information that it should, am I wrong?

* The Logging API Looks good all in all - How do you plan to connect between a job and a turn? That is not so clear from your api header

8. perception.h -
* How about you split the FUCKING PAYLOAD DEPENDING ON WHICH TASK WAS REQUESTED??? HUH CLAUDE!? WHY HOLD THE PAYLOAD FOR THREE DIFFERENT TYPES OF REQUESTS WHEN ONLY ONE SUFFICES! JESUS!
* What is the point of the functor of JobChanged?
* Vision is a bad name. Doesn't describe any intent what so ever.
* What is the point of sam3Turn?
* There is no differentiation between Highlighting with bounding boxes and highlighting with both bboxes & image seg-masks. Why is that the case?
* What is VerifyRelation? How does it work?
* API Seems like its getting there, still half baked in my opinion - You don't really know what the API should be.

9. perf.h -
* PerfEvent@stage shouldnot be a string, unless you plan on chaining subEvents from each system, in which case I'd permit it.
* What is the diff between record and MarkNow? MarkNow() I understand since I have something similar in util2 called mark()/markfmt(...), I don't understand what is the intent of Record? is End its counterpart? If so, why is this not clear from the code itself? Dude, we talked about intent in the code a million times! CLAUDE!
* Where does the writer thread plan to write to?
* How do you plan to actually instrument the code that you're writing? Instrumenting a process is one thing, but we can literally just instrument our code with performance markers. we have that kind of granular control over our code.
* Besides that, it looks good and self contained.

10. recognizer.h -
* What does the recognizer look like in action? Is it literally calling a function or 2 in series? What does the usage of this API Look like externally, also what does the API look like internally? How is everything being used?
* I won't know for sure until I see what I requested of you.

11. runtime.h -
* There shouldn't be a watcher for each process. Is this OS Internal stuff that we don't worry about? Why not use a single thread for this job? The thread will loop over all processes, OR, even better, have a condition variable be enabled as soon as a process fails, after which, it'll be saved into a queue (to make sure that multiple-failure is still safe) that the worker thread handles.

* the naming of your functional API is not good. Intent is not clear enough. Guidelines.md
* I don't understand how you would actually use this API, where-ever it may be.
* Why is RosSubscribe/close here? ROS2 literally offers a this->create_subscription service in C++, is this not the same in Python? Do we have to do something differently? I don't understand.

12. sam3.h -
* Mask@Bits - what?
* Why is there a Sam3Process function, but on the other hand a Connect function?
* Sam3Detect is good. Does it actually reflect our usage of the SAM3 api? or is the SAM3 API offered by transformers more explicit, and therefore should be rewritten more explicitly into the discrete steps the Transformers library offers? What do you think?
* Other than that, looks solid.

13. scripted_run.h -
* I kind of understand the usage, but also not fully? Explain the usage in pseudo-code.
* I don't understand the point with ScriptMain.
* Is this an actual pyhon file or a shell script???
* looks fine besides that.

14. status.h -
* Looks good

15. util.h - no comments here.

16. video.h -
* What is the current connection between the camera source and the gstreamer C++ ROS2 Node?
* Is frameRing owned here? Who has ownership of this framebuffer? clearly this "Video" class is the source of the frames here.
* Video is a bad name. Again, guidelines.md
* Who calls GstreamerProcess?
* Looks fine all in all, besides my questions.

17. app.h -
* Why not pull the Chat out of the Screen Struct to a different struct?
* ScreenAddChat? What is the intent here? what does it actually do?
* Also ScreenRun()? the hell?
* Where is the display Loop actually running?
* Where does all of the initialization happen?
* Alright Looks good all things considered.

Alright, to ensure that you actually address all my issues and not forget anything, here is what we'll do:
0. Re-review the files that you touched, since I compacted your context. For all I care, re-review your handoff document and the files that you've touched so far to get an anchor of where we are. Any document file that you think is relevant should be touched. Tell me what you understand regarding our current local steps, and the global steps.

1. Address EVERY SINGLE POINT THAT I MADE REGARDING EVERY SINGLE(!) FILE! you can give them numbers, i.e -
  1. vision.h -
  1.1 - blah balh blah
  1.2 - ....
  2. perception.h -
  2.2 -
  ...
  and so on

2. After you address all of my points, do the same operation, BUT - Tell me instead what you plan to change by taking into account all of my questions, what do you suggest, etc... These lists per file don't have to address every single point, but can be conslidated instead. Every point that you made here should be backed up by sources - things that you said before, my verdicts, whatever. I want to see that there was a clear line of thought.

3. General points that need to be done throughout all the files.

4. I'll review this once more, I hope that we will be done with this API review by today, to leave the implementation running overnight.
