# Reflecting the Qubes security label on a Razer keyboard

## Why would this be useful ?

[Qubes OS][1] is a Xen-based distribution that allows you to run applications
in isolated containers (technically, paravirtualized guest systems), and
integrate all their windows in seamless mode.

To help the user distinguish the security contexts (and prevent compromised
containers from doing social-engineering attacks by popping seemingly legit
dialogs), Qubes will draw a color-coded border around every window. Every
container (AppVM, in Qubes lingo) will be tagged with one of 8 possible colors,
with a 9th (white) reserved for the administrative domain (Dom0). I would
guess that most users use a rainbow-logical scheme, with the less trusted
domains in red and the most trustworthy in green or blue.

However, if that takes care of output, there still is a risk pertaining to
input. What you type on the keyboard will only get sent to whichever
AppVM currently holds focus, but can you tell with certainty which AppVM has
the focus at any moment ?

I recently acquired a [Razer BlackWidow Chroma v2][2] keyboard, which features a very nifty illumination mechanism; every key contains an RGB LED that can be
independently controlled. 

This would in principle allow the use of a very nice security feature: a
keyboard that changes colors based on which security context is currently
receiving the keypresses. If the keyboard is red, don't type any sensitive passwords !

## Controlling the Razer lighting

Once plugged in, the Razer keyboard exposes itself as a USB device with three
subinterfaces, two of Keyboard types, and one of Mouse type. Wtf ?

Fortunately, the fine folks from [OpenRazer][3] have already performed all the
reverse engineering on their protocol. From their documentation, it appears 
the two keyboard interfaces are used to send keypresses, in two different contexts (normal mode or game mode ?), and the mouse interface allows the host to
send commands to the keyboard, because apparently a mouse is typically allowed
to receive such commands. Why ? absolutely no idea.

In principle, I would expect such a driver to run entirely in userspace, but
OpenRazer provides a few kernel modules. I'm not completely sure about the technical reason, but it may have to relate to being able to control the fancy colors, and at the same time also pass keypress events to the HID stack. 

This isn't a blocker, since I'm running Qubes 4, which runs the USB kernel
drivers in an unprivileged container. However, shipping custom kernel modules
for Qubes is not a completely trivial task, as we will see.

On the good side, the interface exposed by the razerkbd module is really ideal.
You write to files in sysfs to enable the various lighting modes. In particular, there is a `matrix_effect_static` that takes a RGB color coded over 3 bytes,
and will light the entire keyboard accordingly. However, this is unsuitable for
our use case, as this mode will perform a smooth transition when switching
colors. Transition takes about one second, which is too slow for us.

Another mode is `matrix_effect_custom`, which allows you to control the lighting
of every key independently. Another control file, `matrix_custom_frame`, allows
you to configure the lighting by setting a batch of RGB colors for a bunch of contiguous keys on the same row.

We can of course use this to set a single color to all keys, but contrary to
the static mode, this switch is instantaneous.

OpenRazer provides some applications, and a userspace daemon for managing
the keyboard, but I didn't bother looking at it, because the interface exposed
by the kernel driver is really logical and easy to use. For such a simple task,
i'll drive it directly from python. You can find the source in
[this repository][4]. The script will go through sysfs, look for the first
compatible device, and let you drive it conveniently, for instance with:

    from razer import *
    kb = Keyboard()

    # set the keyboard a single color, using static mode (slow)
    kb.color(red)

    # set a single color, using a full frame for fast mapping
    # use a custom RGB color (orange)
    kb.color_fast((255,127,0))

    # configure a custom map and assign it to the keyboard
    m = Map(default=green, layout=qwertz)

    m['esc'] = red
    m['return'] = blue
    kb.custom(m)


## How Qubes support custom kernel modules in the guests

tl;dr it does not. You have to make your hands dirty.

The latest version of Qubes supports two main conterization modes:
Paravirtualization (PV), and Hardware Virtual Machine(HVM). In HVM mode, the
host uses the hardware-assisted virtualization features of the CPU, to trick
the guest into thinking it is running at the highest privilege level. All
interaction with the outside world happens by having the host emulate the
behaviour of real physical devices.

By contrast, in PV mode, the guest is aware that it is running under a
hypervisor. This requires a custom (xen-compatible) kernel and special drivers,
but it doesn't require hardware-assisted virtualization, and is faster because
it can skip emulating a hardware interface.

In particular, that means that in HVM mode, the host emulates a bootable drive
and a BIOS, and the bootloader inside the guest is responsible for driving
the virtual disk, loading the guest kernel into memory, and then running it.
By contrast, in PV mode, the hypervisor directly loads the kernel and then runs it in a separate context.

This means a guest in PV mode cannot choose its own kernel. In fact, AppVM
kernels are installed in the Dom0, and the management system provides the
kernel to Xen whenever it starts a new container. Now, for loadable kernel
modules, the modules should of course agree with the running kernel version.
So modules are provided by Dom0 as well, in the form of a read-only disk image
that is provided to every PV guest, and typically mounted under `/lib/modules/<vrsion>`. It is critical that this mount is read-only, and enforced by the Xen
hypervisor, otherwise an AppVM container could compromise other AppVMs running
the same kernel version.

One apparent obstacle, here, is that the kernel running our PV guests is only installed into the Dom0. Furthermore,
those are Qubes-packaged kernels, and it might not be easy to find exactly the right versions to install into your guest.
But we surely don't want to pull a C compiler into the Dom0 !

Before Linux 2.6, building out-of-tree modules was a horrible mess and was typically difficult to achieve
without the full kernel sources. Since 2.6, there is a new mechanism that allow out-of-tree builds. This works by storing
the build infrastructure under `/lib/modules/<version>/build`. This build infrastructure
contains, among others, a Makefile that will be included by the module Makefile, and will pull the relevant
kernel config options to let the module be built out of tree. So, the good news is that all our PV
guests have access to the build infrastructure for the correct version, out of the box.

## Building the razer driver for Qubes

First of all, the latest *stable* kernel provided by Qubes fails to build. To install the latest guest kernel, you have to
install `kernel-latest-qubes-vm`. Of course, Dom0 never has direct network access, so you have to install it using the
wrapper script `qubes-dom0-update`, which will ask the default firewall VM to download the packages, and then copy them into
Dom0 for installation.

We spin up a disposable Fedora container, and pull the required build dependencies, conveniently packaged
in the `kernel-devel` package. In the current version, there is a broken dep, and you have to also pull `bison`
and `flex` to make the build work fine.

Next obstacle is that the build infrastructure is not mounted read-write. We need to make our own copy of the modules
directory provided by the dom0, and build into it:

    cp -a /lib/modules/$(uname -r) /tmp/rw-modules
    mount --bind /tmp/rw-modules /lib/modules/$(uname -r)

Then, for some strange reason, we have to prepare the build infrastructure:

    cd /lib/modules/$(uname -r)/build
    make gcc-plugins

From there, hopefully the DKMS infrastructure (used by Fedora to build kernel modules) should work out of the box. It so happens
that OpenRazer provides a Fedora repository for that, so we follow the instructions on their website to add their repo and build
the module (i'm using a Fedora 28 template):

    dnf config-manager --add-repo http://download.opensuse.org/repositories/hardware:razer/Fedora_28/hardware:razer.repo
    dnf install openrazer-kernel-modules-dkms

If anything ran smoothly, you should now have a bunch of extra .ko files under /tmp/rw-modules/extra.
These need to be packaged and sent to dom0. We will make a tarball of these:

    cd /tmp/rw-modules
    tar cvf modules.tar extra Modules.*

Along with the actual modules, files like Modules.deps contain the metadata like module dependencies which is used by modprobe
to automatically load dependencies. This needs to be up to date, unless you like loading everything by hand when the container starts

Next, copy the tarball to dom0, by running in the dom0:

    qvm-run -p <APPVM-NAME> "cat /tmp/rw-modules/modules.tar" >modules.tar

Checksum it just in case.

Now, we will copy the new information into the dom0 modules image. Make a backup just in case:

    cd /var/lib/qubes/kernels/<version>
    cp modules.image modules.image.bak

    mkdir /tmp/modules
    mount -o loop modules.image /tmp/modules
    tar xvf ~/modules.tar -C /tmp/modules
    umount /tmp/modules

Start an AppVM with the newer kernel, and you should be able to `sudo modprobe razerkbd` without error.
After that, running the provided python module (as root) should let you play with your colorful keyboard.

## Detecting the currently focused security context

Qubes achieve seamless integration between windows of different containers, by having each container run an X server doing its
own business, but without a standard window manager. Instead, it renders window content into a dummy device backed by fast
Xen-provided shared memory. A pair of daemons exchange events (for instance, window creation) between containers. The X server
running into Dom0 has control of the actual display, and for every window created by an AppVM, it will create a Dom0 window, and render
the contents from the shared memory. The window manager running in Dom0 will then add the colorful borders.

Fortunately, this information is easy to access. Whenever an AppVM create a window, the userspace daemon (`qubes-guid`) will tag the windows
by setting two X properties onto them: `_QUBES_LABEL` contains a byte from 1 to 8, identifying the context, and `_QUBES_LABEL_COLOR` contains
a 32-bit integer containing the RGB color (blue being the LSB).

For detecting focus changes, we can use `xev` to monitor the root window. Whenever a focus change is detected, we will
probe X to get the id of the currently focused window, and try to read its `_QUBES_LABEL` property. If the property
is missing, we assume that the window belongs to Dom0, and we will color it white. Once we have determined the label, we need
to send it to the `sys-usb` VM that controls the Razer keyboard driver.

Originally, I would simply read the RGB color set by the window manager, and configure the keyboard with it. Unfortunately, it doesn't
look very good, as the contrast between screen and keyboard lighting is not exactly the same. I found it simpler to just send the label id
to sys-usb, and then apply my own color table. For reference, the label values 1-8 correspond to the colors red, orange, yellow, green,
grey, blue, purple, and black.

## Piping it all together

The following (disgusting) shell script runs in dom0 and notifies `sys-usb` whenever the window focus changes. Note
that qvm-run is only used once to spawn the controller process. The main function in razer.py reads from stdin,
parses the output from xprop, and writes the relevant settings to the driver control files in /sys.

    xev -root |grep --line-buffered _NET_ACTIVE_WINDOW |while read
    do
        xprop -id $(xdotool getwindowfocus) 0c '=$0\n' _QUBES_LABEL
    done 2>/dev/null |qvm-run -p sys-usb "sudo python3 ./razer.py"

[1]: https://www.qubes-os.org/
[2]: https://www.razer.com/gaming-keyboards-keypads/razer-blackwidow-chroma-v2
[3]: https://github.com/openrazer/
[4]: https://github.com/maugier/qubes-razer-integration
