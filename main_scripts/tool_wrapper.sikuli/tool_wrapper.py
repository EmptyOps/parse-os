# -*- coding: utf-8 -*-

import org.sikuli.script.Location as Location
import org.sikuli.script.Screen as Screen
import org.sikuli.script.Key as Key
import org.sikuli.script.Button as Button 
import time

class ToolWrapper:
    def __init__(self, delay=5):  # ✅ Default delay = 5 seconds
        self.screen = Screen()
        self.delay = delay

    def click(self, x, y):
        self.screen.click(Location(x, y))
        time.sleep(self.delay)

    def type_text(self, x, y, text):
        self.screen.click(Location(x, y))
        self.screen.type(text)

    def scroll(self, x, y, direction):
        self.screen.hover(Location(x, y))
        if direction == "up":
            self.screen.wheel(Location(x, y), Button.WHEEL_UP, 10)   
        elif direction == "down":
            self.screen.wheel(Location(x, y), Button.WHEEL_DOWN, 10)