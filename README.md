SnapVanish
Disappear on camera. Reappear on cue.

SnapVanish is a desktop webcam effects project that uses real-time computer vision and hand gestures to create disappearance, particle, and teleportation-style effects. It supports local camera preview and virtual-camera workflows for video calls and streaming.
Features
- Normal Vanish: Flash a two-finger V sign to fade out of the camera frame.
- Particles: Turn your silhouette into drifting particles with the same V gesture.
- Naruto Vanish: Put your palms together for a smoke-and-substitution effect.
- Goku Mode: Hold two fingers at your forehead to trigger a teleport-style effect.
- Virtual camera: Send effects to a compatible virtual camera backend, or capture the preview window in OBS.
- Local processing: Video effects run on your computer, without sending the webcam feed to a server.
Requirements
- Windows and a working webcam
- Python and the packages listed in requirements.txt for source-based use
- OBS Studio or another compatible virtual-camera backend for virtual-camera workflows
Quick start
Clone the repository and launch the local menu:
git clone https://github.com/ATLURI0001/SnapVanish.git
cd SnapVanish
.\AVVIA_LOCALE.bat
Choose a mode in the startup menu. For background capture, step out of the camera frame for approximately four seconds, then step back in.
Launch with a specific mode
.\AVVIA_LOCALE.bat --mode normal
.\AVVIA_LOCALE.bat --mode particles
.\AVVIA_LOCALE.bat --mode naruto
.\AVVIA_LOCALE.bat --mode goku
Virtual camera / OBS
.\AVVIA_VIRTUAL.bat
For an OBS window-capture workflow, run AVVIA_OBS.bat, add a Window Capture source in OBS, and select the webcam preview window. If using OBS's virtual camera as the app's output, stop OBS Virtual Camera before launching this app so there is no conflict.
Controls
Key	Action
Space	Capture the background again
V	Trigger an effect manually, except in Goku mode
R	Reappear, except in Goku mode
F	Toggle fullscreen
Q or Esc	Exit and release camera devices


Camera settings
.\AVVIA_LOCALE.bat --camera 1 --width 1280 --height 720 --fps 30
Use --gesture-debug to print gesture-recognition diagnostics in the terminal.
Technology
Python · OpenCV · MediaPipe · Real-time image processing · Virtual camera integration
Licensing and provenance
SnapVanish is based on an existing third-party webcam effects codebase. The upstream repository did not include an explicit license file when this document was prepared. Before publishing or distributing modified source code, obtain permission from the copyright holder and preserve any required notices and original Git authorship.

Third-party models, audio, and other assets may have separate license terms.
Responsible use
Only use camera and video effects with permission from the people involved. SnapVanish is designed for creative effects, demonstrations, and streaming—not impersonation or deceptive recordings.
