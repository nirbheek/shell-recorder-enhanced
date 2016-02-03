On GNOME Shell, uses the org.gnome.Shell.Screencast DBus API to record the
contents of an attached display.

On startup, asks which display to record, records sound from the default device,
and optionally overlays the contents of a selected Webcam on top of the screen
recording at the bottom right corner.

Usage: python3 record.py &lt;filename&gt;
