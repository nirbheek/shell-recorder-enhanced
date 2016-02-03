#!/usr/bin/env python3
# vim: set sts=4 sw=4 et tw=0 :
#
# Author: Nirbheek Chauhan <nirbheek.chauhan@gmail.com>
# License: MIT
#

import gi, sys, time
gi.require_version ('Gst', '1.0')
from gi.repository import Gio, GLib, Gst

Gst.init(None)

def get_displays():
    display_p = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE, None,
            # Let's make the owner the shell itself instead of owning a bus name
            # of our own. It doesn't really matter.
            "org.gnome.Shell",
            "/org/gnome/Mutter/DisplayConfig",
            "org.gnome.Mutter.DisplayConfig",
            # We want to do this synchronously
            None)

    displays = display_p.call_sync("GetResources", None,
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
            "name": "{} {}".format(metadata["display-name"], metadata["product"]),
            "connector-type": metadata["connector-type"],
            "presentation": metadata["presentation"], # No idea what this is
            "primary": metadata["primary"],
        }
        # Append a tuple of (display_details, (x, y, width, height))
        displays_info.append((details, area))
    return displays_info

def read_index():
    index = None
    while True:
        try:
            index = int(input())
        except ValueError:
            print("Invalid index, try again\n> ", end="", flush=True)
            continue
        else:
            break
    return index

def select_display(displays):
    ii = 0
    print("Select a display to screencast:")
    for (display, area) in displays:
        print("[{}] {}, connected via {}".format(ii, display['name'],
                display['connector-type']),
            end="", flush=True)
        if display['presentation']:
            print(" (presentation)", end="", flush=True)
        if display['primary']:
            print(" (primary)")
        else:
            print("")
        ii += 1
    print("> ", end="")
    return displays[read_index()]

def select_webcam(webcams):
    print("Select a webcam to overlay:")
    print("[0] No webcam")
    ii = 1
    for webcam in webcams:
        print("[{}] {}".format(ii, webcam.get_display_name()))
        ii += 1
    print("> ", end="", flush=True)
    index = read_index()
    if index == 0:
        return None
    return webcams[index - 1]

def find_closest_caps(devcaps, req_width):
    devcaps = devcaps.intersect(Gst.Caps.from_string("image/jpeg"))
    if devcaps.is_empty():
        return None
    ii = devcaps.get_size() - 1
    retcaps = Gst.Caps.new_empty()
    # We start from the end (smallest resolution), find the point where we
    # either match the requested width or exceed it, and immediately return it
    while ii >= 0:
        s = devcaps.get_structure(ii)
        swidth = s.get_int("width")[1]
        if swidth < req_width:
            ii -= 1
            continue
        if swidth >= req_width:
            s.fixate()
            retcaps.append_structure(s)
            return retcaps
    return None

def caps_to_placement(caps, width, height):
    w = caps.get_structure(0).get_int("width")[1]
    h = caps.get_structure(0).get_int("height")[1]
    ratio = w/h
    # If the overlay size is significantly off what we want, do scaling
    if width//w < 3 or height//h < 3:
        h = height//4
        w = int(h*ratio)
    return ((width - (w + 10)), (height - (h + 10)), w, h)

def screencast_area(filename, area, webcam):
    if webcam:
        webcam_device = webcam.props.device_path
    else:
        webcam_device = None

    pipeline_str = "compositor name=c background=black "
    if webcam_device:
        width = area[2]
        height = area[3]
        # We scale the overlay to be 1/16th the size of the screen
        closecaps = find_closest_caps(webcam.get_caps(), width//4)
        if not closecaps:
            return (None, False, None)
        (xpos, ypos, owidth, oheight) = caps_to_placement(closecaps, width, height)
        pipeline_str += "sink_1::zorder=1 sink_0::zorder=2 "
        pipeline_str += "sink_0::xpos={} sink_0::ypos={} sink_0::width={} sink_0::height={}\n".format(xpos, ypos, owidth, oheight)
        pipeline_str += "v4l2src device={} ! {} ! jpegdec ! queue ! c.sink_0\n".format(webcam_device, closecaps.to_string())
    pipeline_str += """
    matroskamux streamable=true name=m
    pulsesrc ! audioconvert ! opusenc ! queue name=audioq ! m.
    c. ! queue name=coutq ! vp8enc min_quantizer=13 max_quantizer=13 cpu-used=5 deadline=1000000 threads=%T ! queue name=videoq ! m.
    queue name=shellq ! c.sink_1
    """
    print("Pipeline:\n" + pipeline_str)
    pipeline = GLib.Variant.new_string(pipeline_str)
    params = area + (filename, {'pipeline': pipeline})

    cast_p = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE, None,
            # Let's make the owner the shell itself instead of owning a bus name
            # of our own. It doesn't really matter.
            "org.gnome.Shell",
            "/org/gnome/Shell/Screencast",
            "org.gnome.Shell.Screencast",
            # We want to do this synchronously
            None)
    ret = cast_p.call_sync("ScreencastArea",
            # Write to test.webm, with no options
            GLib.Variant("(iiiisa{sv})", params),
            Gio.DBusCallFlags.NONE, -1, None).unpack()
    return (cast_p,) + ret

filename = "test.mkv"
if len(sys.argv) > 1:
    filename = sys.argv[1]

print ("Probing webcams...")
dm = Gst.DeviceMonitor()
dm.add_filter("Video/Source")
dm.start()
devices = dm.get_devices()
dm.stop()

(display, area) = select_display(get_displays())
(stop_p, ret, f) = screencast_area(filename, area, select_webcam(devices))

if not ret:
    exit(1)

print("Casting screen '{0}' to '{1}'".format(display['name'], f))

# Record for 10 seconds. Ideally we want a mainloop here or something.
time.sleep(60)

stop_p.call_sync("StopScreencast", None, Gio.DBusCallFlags.NONE, -1, None)
