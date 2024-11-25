import cv2 as cv


color_maps = {
    "Jet": cv.COLORMAP_JET,
    "Hot": cv.COLORMAP_HOT,
    "Cool": cv.COLORMAP_COOL,
    "Spring": cv.COLORMAP_SPRING,
    "Summer": cv.COLORMAP_SUMMER,
    "Autumn": cv.COLORMAP_AUTUMN,
    "Winter": cv.COLORMAP_WINTER,
    "Rainbow": cv.COLORMAP_RAINBOW,
    "Ocean": cv.COLORMAP_OCEAN,
    "Pink": cv.COLORMAP_PINK,
    "HSV": cv.COLORMAP_HSV,
    "Parula": cv.COLORMAP_PARULA,
    "Magma": cv.COLORMAP_MAGMA,
    "Inferno": cv.COLORMAP_INFERNO,
    "Plasma": cv.COLORMAP_PLASMA,
}

display_resolutions = { "480x320":[480,320], 
                        "640x480":[640,480],
                        "800x600":[800,600],
                        "1024x768":[1024,768],
                        "1280x1024":[1280,1024],
                        "1920x1080":[1920,1080]
}

display_interpolations = {
    "Nearest": cv.INTER_NEAREST,
    "Linear": cv.INTER_LINEAR,
    "Cubic": cv.INTER_CUBIC,
    "Area": cv.INTER_AREA,
    "Lanczos4": cv.INTER_LANCZOS4    
}

sample_rates = {
    "1 Hz": 1,
    "2 Hz": 2,
    "4 Hz": 3,
    "8 Hz": 4,
    "16 Hz": 5,
    "32 Hz": 6,
    "64 Hz": 7
}

baudrates = [
    57600,
    115200,
    230400,
    460800,
    921600
]

help_table = [
    ["Key", "Function"],
    ["Esc, q", "Exit the program"],
    ["Space, p", "Pause the video"],
    ["M", "Change the color map"],
    ["C", "Capture the current frame"],
    ["H", "Toggle the help"],
    ["D", "Change the display resolution"],
    ["I", "Change the display interpolation"],
    ["T", "Show temperature contours"],
    ["O", "Show min max points"],
    ["D", "Change the display resolution"],
    ["B", "Debug mode"],
]