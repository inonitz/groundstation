# The owner's review of the rev3 headers, round 1 (2026-10-02), word for word

1. audio.h -
* source should be a constexpr/const variable/enum, there are literally 2 options here, should not be a generic string.
* Why is phoneASR so fucking bulky? What the hell? It should not be this big.
* what do you mean by "void** sources"? This is not specific at all. What do the pointers point to? What do they call in each class?
* LaptopTTS is horrible. I can't know anything here.
* What is the point of "names" inside SpeechOut? We have a vector of outputs, sure.
* Why does SpeechOut need a handle to perf? Anyways, SPeechOut should be smaller, shouldn't be more than a thread with a std conditional_variable, an atomic bool, and a list of all speech sources. Might be wrong here. Furthermore, what is the point of handling the vector of outputs? What do we do with it? I can't infer the internal logic from these structures.

The functional API looks fine? a little barebones?
This is our current design, which is far from the ideal one (which I'll sketch below):

Ideal:
                                  (Uniform API)
Microphone Sources ===========> Transcription Model ===========> Resulting Text ===========> ROS2 Network

Current:
Path A -
                          (hardware connected)                                               (Internally does)
Laptop Source ======================> C++ Model backend ======================> ROS2 Network to /transcription/raw ===========> ros2_asr.py

 Path B -
                                                                                                                            WIFI
Phone Mic Source ===========> Google Transcription Models (Android) ===========> HTTP Server ===========> phone_asr.py

Each of these python files should somehow make the interface to both API's "Uniform", even though both of them work differently.

2. control.h -
* Control is a bad word. This is effectively the flight controller on the software side.
* ControlManualOn should be CotrolManualState(bool desired_state), unless I misunderstood the intent here
* Dude what the fuck is the point of each function here? This API is fucking garbage. too many functions, not simple enough.
* Why is there a race condition here? We don't need a lock! Just use an atomic flag to toggle the manual mode switch. The voice thread should run regardless, we just ignore its output? i don't understand claude.

3. dji_app.h -
* Great functional API. I don't understand why "probing" is a thing or what its used for. This also applies to the Status struct and the OnEvent func

4. gemma4.h -
* Why do we need 2 APIs to initialize gemma? When we initialize gemma as a "process" / "service" we should be able to call it just by giving its handle and our normal llama-server Json Header form like in GemmaRequest. Same deal with GemmaClose() ==> What do you mean "GemmaClose"? If we have a gemma  process, how can we actually "close" it? Are we responsible for it? why do we also need to "create" the process again if we already initialized its process??

5. keys.h -
* Looks good. I don't know why we need a full-blown process/service just for handling the keys, when in reality all we do is just wrap around the ROS2 /transcribe/raw with a subscription node of our own, but alright. If that constitues enough for you to create a whole process, instead of being just a part of KeysCreate() & keysClose() then find. Also note - Can the "Keys Process" Really fail that we might need to restart it?

6. log.h -
* Why does the Turn Struct need the "perceptionDir" ? What is the meaning of this variable? * Furtheremore, what if there was no vision Query? What if the query was simply describe? Why is there no enum to fill out what the query was actually decided as?
* The Raw data should be here, Then the data from the recognizer, then the data from the vision query itself all organized properly.

* Why does SessionLog need to keep "tl", I don't understand. I also don't understand the purpose of "claimed" & seq.

* How would the Log API work in reality? show me a demonstration of the API were we to actually use it in C
* Regarding the perf module, it looks good, just probably needs to split into perf.py
* I don't see that the turns are actually encapsulated inside SessionLog

7. perception.h -
* I don't understand what actually happens in the perception engine. Rewrite, specifically I don't understand PerceptionEngine.

8. recognizer.h -
* What is the diff between RecognizerRoute,RecognizerAct and the Recognize(), also Plan()????
* The warmup should happen inside Create(), maybe with a flag to not do so for whatever reason.

9. runtime.h -
* Why does a status carry a lock?
* What is the point of "procs"?
* I don't understand, is the Supervisor Class granular to a single service or is it the list of processes/services we're running?
* Why is statusBoard part of the runtime.h ?
* I don't understand why you need a supProcess when you already have a Process Struct.
* What is the point of SysPackage?
* You don't need a single function to start/stop ROS. you literally just init the ROS2 Node with a subscriber and call it a day. I don't understand. am I missing something here?

10. sam3.h -
* what is the point of quantize when there is precision? Why aren't these enums?
* Why hold the lock inside the SAM3 backend?
* API Looks good other than that.
* we should probably think of how we put SAM3 inside its own service/process RIGHT NOW, if we already have a process/service API.

11. util.h - Looks good

12. video.h -
Looks fine? Haven't taken a good look yet.

Review all of my points. you have 26% context left. We will use this to devise a proper API, and as I previously said, we will let another agent handle the implementation. This places the burden on you to create a proper API with me.
