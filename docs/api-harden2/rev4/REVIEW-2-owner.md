# The owner's review, round 2 (2026-10-02), word for word (answers to the agent's round-1 replies)

1. audio.h - Show me what it'd look like
2. control.h -
* Yes
* Yes
* Isn't the current Control api a simple wrapper to create a generic way, if we, in the future, create more interfaces for other platforms?
* Show me the revision

3. dji_app.h -
* What do you mean? you have a background thread pinging the status of the connection once every 2 seconds?

4. gemma.h - What do you mean? Every gemmaStart creates a unique llama-server? Is this really what you're saying?

5. Right, Sorry I forgot. You're completely correct. my bad.

6. log.h -
* I see. This should not be inside a turn. This is not granular to a single turn.
* True. But why call it "tl". what the fuck does this mean? seq - Sure, claimed - what does this look like? CLAUDE!

7. perception.h -
* Sure.

8. recognizer.h -
* WHAT IS ACTUALLY BEING USED OUTSIDE??? YOURE NOT CREATING AN API FOR A LIBRARY! YOURE CREATING AN API FOR ME! TO UNDERSTAND THE INTERNALS AND UNDERSTAND THE INTENT! IF YOU WERE CREATING A LIBRARY WE WOULD GO ABOUT THIS COMPLETELY DIFFERENTLY
* You are not clear enough with your explanation. Furthermore, if your API doesn't explain itself, then its not good.

9. runtime.h -
* Don't hide anything. Same as point 8.
* Good changes, I'd like to see the revision.

10. Sam3 -
* We already said that we don't  do ANY! CHANGES! TO THE WEIGHTS! AT RUNTIME! EVERYTHING IS PRESAVED AS SUCH! IM NOT GOING TO LOAD A Q8 MODEL AND THEN QUANTIZE IT AT RUNTIME! WE HAVE BEEN OVER THIS CLAUDE!
* Masks should be per frame, as it doesn't make sense to decouple the masks from the frame itself.
* Dude, why didn't you fucking read them? THEYRE RELEVANT TO YOUR DESIGN! SO YOU SHOULD READ THEM!
* alright. Now that you have a shared memory-ring, what now? How do you plan to utilize it? How do you plan to deal with the fact that you need to save frames with their bboxes? How do you plan to transfer the video frames directly into the memory-ring, s.t. requests would not be delayed by memory transfers?

Regarding the rest of the files I haven't reviewed -
video.h -
* why does video hold a process? it should not have ownership here - Does the Video Stream Hold ownership of the ROS Stream? (This point is negated by the last point)
* what is the point of VideoSourceKindOf?
* Why does it look like the whole API is designed around the gstreamer process? Nevermind I now remember why. we only use the gstreamer ROS2 Node, why do you make this code so obscure to not realize that? This looks like a gstreamer class That was patched to accomodate video streams from files, which is shit. Requires rework.

* app.h -
* why did you not update it already?
* Why is OnKeyPress and OnKeyRelease here? Isn't this already inside keys.h?
* TurnHandler not completely relevant anymore with the new design
* AppVisionSinks? What do you mean exactly here?
* Why is half of the vision API data Inside ScreenState? The Vision API should be borrowed and not restated here.
* Why is there a lambda for ManualOn inside the Ui Struct?
* Looks fine besides that.
