#Application to read the thermal camera data and display it on the screen
#Read the data from serial port
#Data format is csv 
#768 pixels in 32x24 format
#Each pixel is corrected temperature in DegC
#Arrange the pixels in a 2x2 array to be displayed as colour according to temperature

#User interface has option for serial port selection
#Option to select the display mode
#Option to select the colour map


import serial
from serial.tools.list_ports import comports
import time
import tkinter as tk
from tkinter import ttk
import numpy as np
import cv2 as cv
import configparser
import os


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

class IRCamApp(tk.Tk):
    def __init__(self, port="", color_map="jet", *args, **kwargs):
        tk.Tk.__init__(self, *args, **kwargs)
        self.request_disconnect = False
        self.title("IR Camera")
        self.geometry("640x480")
        self.port = port
        self.color_map_default = color_map
        self.overlay = True
        self.display_room_temp_in_range = False
        self.display_range_headroom = 2
        self.display_max_temp_autorange = True
        self.display_min_temp_autorange = True
        self.display_max_temp_manual = 40.0
        self.display_min_temp_manual = 10.0
        self.display_resolution = display_resolutions["640x480"]
        self.create_widgets()
        
    def create_widgets(self):
        self.port_label = tk.Label(self, text="Serial Port")
        self.port_label.grid(row=0, column=0)
        
        #dropdown to select the serial port
        self.port_var = tk.StringVar()
        self.port_var.set(self.port)
        self.port_dropdown = ttk.Combobox(self, textvariable=self.port_var)
        self.port_dropdown.grid(row=0, column=1)
        
        self.port_button = tk.Button(self, text="Connect", command=self.connect)
        self.port_button.grid(row=0, column=2)
        
        #color maps chooser
        self.color_map_label = tk.Label(self, text="Color Map")
        self.color_map_label.grid(row=1, column=0)
        
        self.color_map_var = tk.StringVar()
        self.color_map_var.set(self.color_map_default)
        self.color_map_dropdown = ttk.Combobox(self, textvariable=self.color_map_var)
        self.color_map_dropdown["values"] = list(color_maps.keys())
        self.color_map_dropdown.grid(row=1, column=1)
        
        #display resolution chooser
        self.display_resolution_label = tk.Label(self, text="Display Resolution")
        self.display_resolution_label.grid(row=2, column=0)
        self.display_resolution_var = tk.StringVar()
        self.display_resolution_var.set("640x480")
        self.display_resolution_dropdown = ttk.Combobox(self, textvariable=self.display_resolution_var)
        self.display_resolution_dropdown["values"] = list(display_resolutions.keys())
        self.display_resolution_dropdown.grid(row=2, column=1)
        
        #display interpolation chooser
        self.display_interpolation_label = tk.Label(self, text="Display Interpolation")
        self.display_interpolation_label.grid(row=3, column=0)
        self.display_interpolation_var = tk.StringVar()
        self.display_interpolation_var.set("Cubic")
        self.display_interpolation_dropdown = ttk.Combobox(self, textvariable=self.display_interpolation_var)
        self.display_interpolation_dropdown["values"] = list(display_interpolations.keys())
        self.display_interpolation_dropdown.grid(row=3, column=1)
        
        
        self.update_serial_ports()
        
    def update_serial_ports(self):
        self.port_dropdown["values"] = []
        ports = comports()
        for port, desc, hwid in sorted(ports):
            print("{}: {} [{}]".format(port, desc, hwid))
            self.port_dropdown["values"] = [port for port, desc, hwid in ports]
    
    def connect(self):
        port = self.port_var.get()
        try:
            self.ser = serial.Serial(port, 115200)
        except Exception as e:
            print("Error connecting: %s" % e)
            return
        
        self.request_disconnect = False
        #set button text to disconnect
        self.port_button.config(text="Disconnect", command=self.disconnect)
        self._read_data()
        
    def disconnect(self):
        self.request_disconnect = True
        
    def _read_data(self):
        if self.request_disconnect:
            self.ser.close()
            self.port_button.config(text="Connect", command=self.connect)
            cv.destroyAllWindows()
            self.update_serial_ports()        
            return
        
        try:
            str_data = self.ser.readline().strip()
            str_data = str_data.decode("utf-8")
            split_data = str_data.split(",")
            split_data = split_data[0:768]
            #Convert str to float
            data = [float(x) for x in split_data]
        except Exception as e:
            print("Error reading data: %s" % e)
            self.after(500, self._read_data)
            return
        self._process_data(data)
        self.after(100, self._read_data)
        
    def _process_data(self, data):
        data = np.array(data, dtype=np.float32)
        self._display_data(data)
        
    def input_pixel_to_output_pixel(self, x, y):
        #convert input pixel to output pixel
        #input pixel is 32x24
        #output pixel is self.display_resolution
        output_x = int(x * self.display_resolution[0] / 32)
        output_y = int(y * self.display_resolution[1] / 24)
        return output_x, output_y
        
    def _display_data(self, data):
        try:
            data = data.reshape(24, 32)
        except Exception as e:
            print("Error reshaping data: %s" % e)
            return
        
        #reverse the x axis
        data = np.fliplr(data)
                
        min_temp = np.min(data)
        max_temp = np.max(data)
        

        display_min_range = self.display_min_temp_manual
        display_max_range = self.display_max_temp_manual

        if self.display_min_temp_autorange:
            display_min_range = min_temp - self.display_range_headroom
            if self.display_room_temp_in_range:
                display_min_range = min(display_min_range, 20)

        if self.display_max_temp_autorange:
            display_max_range = max_temp + self.display_range_headroom
            if self.display_room_temp_in_range:
                display_max_range = max(display_max_range, 20)
        
        range = display_max_range - display_min_range
        normalized = (data - display_min_range) / range
        
        #convert array to CV_8UC1
        cv_normalized = np.array(normalized * 255, dtype=np.uint8)
        
        color_map_str = self.color_map_var.get()
        color_map = color_maps[color_map_str]
        rgb = cv.applyColorMap(cv_normalized, color_map)
        
        #rescale the image to self.display_resolution_var
        display_resolution_var = self.display_resolution_var.get()
        self.display_resolution = display_resolutions[display_resolution_var]
        display_interpolation = display_interpolations[self.display_interpolation_var.get()]
        rgb = cv.resize(rgb, self.display_resolution, interpolation=display_interpolation)

        #find index of min and max temp
        min_index = np.unravel_index(np.argmin(data), data.shape)
        max_index = np.unravel_index(np.argmax(data), data.shape)

        #swapaxis on the index
        min_index = min_index[::-1]
        max_index = max_index[::-1]
        
        min_pixel = self.input_pixel_to_output_pixel(*min_index)
        max_pixel = self.input_pixel_to_output_pixel(*max_index)


        #print min and max temp on the image
        cv.putText(rgb, "Min: %.2f" % min_temp, (10, 20), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        cv.putText(rgb, "Max: %.2f" % max_temp, (10, 40), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        
        #add overlay
        if self.overlay:
            
            # #print min and max temp index on the image
            # cv.putText(rgb, "Min idx: %d, %d" % min_index, (10, 60), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            # cv.putText(rgb, "Max idx: %d, %d" % max_index, (10, 80), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            
            # #print min and max pixel on the image
            # cv.putText(rgb, "Min px: %d, %d" % min_pixel, (10, 100), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            # cv.putText(rgb, "Max px: %d, %d" % max_pixel, (10, 120), cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            
            #draw min and max pixel circles on the image
            cv.circle(rgb, min_pixel, 10, (0, 0, 0), 1)
            cv.circle(rgb, max_pixel, 10, (255, 255, 255), 1)

        #Use cv to show the image
        cv.imshow("IR Camera", rgb)
        key = cv.waitKey(1)
        
        if key == 27:
            self.request_disconnect = True
            self.ser.close()
            self.destroy()
        elif key == ord("c"):
            #capture the image to the capture folder with timestamp
            folderpath = os.path.join(os.getcwd(), "capture")
            os.makedirs(folderpath, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = "ir_cam_%s.png" % timestamp
            filepath = os.path.join(folderpath, filename)
            cv.imwrite(filepath, rgb)
            #write the data to a csv file in the same folder
            data_filename = "ir_cam_%s.csv" % timestamp
            data_filepath = os.path.join(folderpath, data_filename)
            np.savetxt(data_filepath, data, delimiter=",", fmt="%.2f")
        elif key == ord("p"):
            #pause the display
            cv.waitKey(0)
        elif key == ord("o"):
            #enable/disable the information overlay
            self.overlay = not self.overlay
        elif key == ord("r"):
            #cycle through the display resolutions
            res_keys = list(display_resolutions.keys())
            res_index = res_keys.index("%dx%d" % tuple(self.display_resolution))
            res_index = (res_index + 1) % len(res_keys)
            self.display_resolution_var.set(res_keys[res_index])
            
            

        


def main():
    config = configparser.ConfigParser()
    #add config for last used port
    config.add_section("Serial")
    config.set("Serial", "port", "")
    config.add_section("Display")
    config.set("Display", "color_map", "Jet")
    
    config.read("ir_cam.ini")
    port = config.get("Serial", "port")
    color_map = config.get("Display", "color_map")
    
    app = IRCamApp(port=port, color_map=color_map)    
    app.mainloop()
    
    config.set("Serial", "port", app.port_var.get())
    config.set("Display", "color_map", app.color_map_var.get())
    
    with open("ir_cam.ini", "w") as f:
        config.write(f)
    
if __name__ == "__main__":
    main()   
