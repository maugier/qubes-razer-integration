import pathlib
import re
import sys

red = (255, 0, 0)
green = (0, 255, 0)
blue = (0, 0, 255)
cyan = (0, 255, 255)
magenta = (255, 0, 255)
yellow = (255, 255, 0)
white = (255, 255, 255)

purple = (127, 0, 255)
orange = (255, 127, 0)
grey = (127, 127, 127)
black = (63, 63, 63)


class Keyboard:
    def __init__(self):
        for device in pathlib.Path('/sys/bus/hid/drivers/razerkbd').iterdir():
            if not device.is_dir():
                continue

            if (device / 'matrix_effect_static').exists():
                self.path = device
                return

        raise Exception("Could not locate device")

    def color(self, color):
        (r, g, b) = color
        with (self.path / 'matrix_effect_static').open('wb') as f:
            f.write(bytes((r, g, b)))

    def color_fast(self, color):
        self.custom(Map(default=color))

    def custom(self, custom):
        with (self.path / 'matrix_custom_frame').open('wb') as f:
            f.write(bytes(custom.frame()))

        with (self.path / 'matrix_effect_custom').open('wb') as f:
            f.write(b'1')

default_zones = {
        'letters': list("qwertzuiopasdfghjklyxcvbnm<,.-éàè$"),
        'arrows': ['up', 'down', 'left', 'right'],
        'digits': list("1234567890"),
        'fx': ['f' + str(i) for i in range(1, 13)],
        'mx': ['m' + str(i) for i in range(1, 6)],
    }


class Layout:
    def __init__(self, grid, zones=default_zones):
        self.layout = {k: (x, y) for x in range(6)
                                 for y in range(22)
                                 for k in (grid[x][y],)
                                 if k is not None}
        self.zones = zones

    def __iter__(self):
        return iter(self.layout)

    def __getitem__(self, idx):
        return self.layout[idx]


qwertz = Layout      ([ [None, 'esc', None] + ['f' + str(i+1) for i in range(12)] + ['prtsc', 'scrlk', 'break'] + [None]*4,
                        ['m1', '§'] + [str(i) for i in range(1,10)] + ['0', "'", '^', 'backspace','insert','home','pgup','numlk','/','*','-'],
                        ['m2','tab'] + list("qwertzuiopè¨") + ['return', 'del', 'end', 'pgdown', 'num7', 'num8', 'num9', '+'],
                        ['m3', 'capslk'] + list("asdfghjkléà$") + [None]*4 + ['num4', 'num5', 'num6', None],
                        ['m4','shift'] + list("<yxcvbnm,.-") + [None, 'rshift', None, 'up', None, 'num1', 'num2', 'num3', 'enter'],
                        ['m5', 'ctrl', 'win', 'alt'] + [None]*3 + [' '] + [None]*3 + ['altgr','fn','menu','rctrl','left','down','up',None,'num0','num.',None]])


class Map:

    def __init__(self, default=green, layout=qwertz):
        self.map = [[default for _ in range(22)] for _ in range(6)]
        self.layout = layout

    def frame(self):
        for row in range(6):
            yield row
            yield 0
            yield 21
            m = self.map[row]
            for col in range(22):
                yield from m[col]

    def set(self, index, value):
        (x, y) = self.layout[index]
        self.map[x][y] = value

    def __setitem__(self, index, value):
        zone = self.layout.zones.get(index)
        if zone is not None:
            for k in zone:
                self.set(k, value)
        else:
            self.set(index, value)

    def __getitem__(self, index):
        (x, y) = self.layout[index]
        return self.map[x][y]

    def coloring(self, coloring):
        for (color, keys) in coloring:
            for key in keys:
                self[key] = color

horizontal = Map()
horizontal.map = [[color] * 22 for color in [red,yellow,green,cyan,blue,magenta]]

vertical = Map()
vertical.map = [ ([red,yellow,green,cyan,blue,magenta] * 4)[0:22]] * 6

label_colors = {
        1: red,
        2: orange,
        3: yellow,
        4: green,
        5: grey,
        6: cyan,
        7: purple,
        8: grey
    }


def main():

    dom0 = re.compile("_QUBES_LABEL:  not found.")
    found = re.compile("_QUBES_LABEL\\(CARDINAL\\)=(\\d+)")

    kb = Keyboard()
    kb.color_fast(white)

    for line in sys.stdin:
        if dom0.match(line):
            kb.color_fast(white)
        else:
            m = found.match(line)
            if m:
                color = m.group(1)
                kb.color_fast(label_colors[int(color)])
            else:
                print("Unknown line: {}".format(line))

if __name__ == '__main__':
    main()
