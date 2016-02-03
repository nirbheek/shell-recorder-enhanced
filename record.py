#!/usr/bin/env python3
# vim: set sts=4 sw=4 et tw=0 :
#
# Author: Nirbheek Chauhan <nirbheek.chauhan@gmail.com>
# License: MIT
#

import sys, time
from gi.repository import Gio, GLib

def get_displays():
    display_p = Gio.DBusProxy.new_for_bus_sync (Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE, None,
            # Let's make the owner the shell itself instead of owning a bus name
            # of our own. It doesn't really matter.
            "org.gnome.Shell",
            "/org/gnome/Mutter/DisplayConfig",
            "org.gnome.Mutter.DisplayConfig",
            # We want to do this synchronously
            None)

    displays = display_p.call_sync ("GetResources", None,
            Gio.DBusCallFlags.NONE, -1, None).unpack()
    # displays is a weird structure filled with numbers; extract what we need out of it
    displays_placement = displays[1]
    displays_metadata = [key[-1] for key in displays[2]]
    displays_info = []
    for (metadata, placement) in zip(displays_metadata, displays_placement):
        # Extract the precise area on the entire canvas that this display is shown
        area = placement[2:6]
        if area[0] < 0 or area[1] < 0 or area[2] <= 0 or area[3] <= 0:
            # Remove invalid or useless displays
            continue
        # Extract some identifying details about this display
        details = {
            "name": "{0} {1}".format(metadata["display-name"], metadata["product"]),
            "connector-type": metadata["connector-type"],
            "presentation": metadata["presentation"], # No idea what this is
            "primary": metadata["primary"],
        }
        # Append a tuple of (display_details, (x, y, width, height))
        displays_info.append((details, area))
    return displays_info

def select_display(displays):
    ii = 0
    print ("Select a display to screencast:")
    for (display, area) in displays:
        print ("[{0}] {1}, connected via {2}".format(ii, display['name'],
                display['connector-type']),
            end="", flush=True)
        if display['presentation']:
            print (" (presentation)", end="", flush=True)
        if display['primary']:
            print (" (primary)")
        else:
            print ("")
        ii += 1
    print ("> ", end="")
    while True:
        try:
            index = int(input())
        except ValueError:
            print ("Invalid index, try again\n> ", end="", flush=True)
            continue
        else:
            break
    return displays[index]

def screencast_area(filename, area):
    cast_p = Gio.DBusProxy.new_for_bus_sync (Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE, None,
            # Let's make the owner the shell itself instead of owning a bus name
            # of our own. It doesn't really matter.
            "org.gnome.Shell",
            "/org/gnome/Shell/Screencast",
            "org.gnome.Shell.Screencast",
            # We want to do this synchronously
            None)

    # In theory, we can extend this to add a v4l2src source and record the
    # webcam too, but that was buggy in my testing. The audio went out of whack
    # and the timestamps were all messed up. This was when using compositor to
    # overlay one video on top of the other.
    pipeline_str = """
    matroskamux streamable=true name=m
    pulsesrc ! audioconvert ! opusenc ! queue name="audioq" ! m.
    vp8enc min_quantizer=13 max_quantizer=13 cpu-used=5 deadline=1000000 threads=%T ! queue name="videoq" ! m.
    """
    pipeline = GLib.Variant.new_string (pipeline_str)

    params = area + (filename, {'pipeline': pipeline})
    ret = cast_p.call_sync ("ScreencastArea",
            # Write to test.webm, with no options
            GLib.Variant("(iiiisa{sv})", params),
            Gio.DBusCallFlags.NONE, -1, None).unpack()
    return (cast_p,) + ret

filename = "test.mkv"
if len(sys.argv) > 1:
    filename = sys.argv[1]

(display, area) = select_display(get_displays())
(stop_p, ret, f) = screencast_area (filename, area)

if not ret:
    exit(1)

print ("Casting screen '{0}' to '{1}'".format(display['name'], f))

# Record for 10 seconds. Ideally we want a mainloop here or something.
time.sleep(10)

stop_p.call_sync("StopScreencast", None, Gio.DBusCallFlags.NONE, -1, None)
