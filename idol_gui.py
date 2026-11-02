import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk
from scipy import ndimage

GAUSSIANS = ['65536', '131072', '262144', '524288', '1048576']
OUTPUT_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'Idol Outputs')

# pythonw has no console, so sys.stdout/stderr are None and progress bars crash on write
if sys.stdout is None or sys.stderr is None:
    log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'idol_gui.log'), 'a', buffering=1,
               encoding='utf-8')
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def clean_fake_background(image):
    """Paint a light, colourless background (e.g. a baked-in transparency checkerboard) solid white, so the
    background remover isn't confused by it. Only pixels connected to the image border are touched."""
    if image.mode == 'RGBA' and image.getchannel(3).getextrema()[0] < 255:
        return image
    rgb = np.asarray(image.convert('RGB')).astype(np.int16)
    light_grey = (rgb.max(2) - rgb.min(2) < 18) & (rgb.min(2) > 170)
    border = np.concatenate([light_grey[0], light_grey[-1], light_grey[:, 0], light_grey[:, -1]])
    if border.mean() < 0.8:
        return image
    labels, _ = ndimage.label(light_grey)
    edge_labels = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    background = np.isin(labels, edge_labels[edge_labels > 0])
    rgb[background] = 255
    return Image.fromarray(rgb.astype(np.uint8))


class App:
    def __init__(self, root):
        self.root = root
        self.pipeline = None
        self.image_path = None
        self.preview_ref = None
        root.title('Idol: Image to 3D')
        root.geometry('760x560')

        controls = ttk.Frame(root, padding=12)
        controls.pack(side='left', fill='y')

        ttk.Button(controls, text='Choose image...', command=self.choose_image).pack(fill='x')
        self.file_label = ttk.Label(controls, text='No image selected', wraplength=220)
        self.file_label.pack(fill='x', pady=(4, 12))

        ttk.Label(controls, text='Image type').pack(anchor='w')
        self.mode = tk.StringVar(value='synthetic')
        ttk.Radiobutton(controls, text='Render / AI image', variable=self.mode, value='synthetic').pack(anchor='w')
        ttk.Radiobutton(controls, text='Real photo', variable=self.mode, value='real').pack(anchor='w')

        self.clean_bg = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text='Fix fake checkerboard background', variable=self.clean_bg).pack(
            anchor='w', pady=(8, 0))

        ttk.Label(controls, text='Detail (number of Gaussians)').pack(anchor='w', pady=(12, 0))
        self.gaussians = tk.StringVar(value='262144')
        ttk.Combobox(controls, textvariable=self.gaussians, values=GAUSSIANS, state='readonly').pack(fill='x')

        ttk.Label(controls, text='Steps (more = slower, better)').pack(anchor='w', pady=(12, 0))
        self.steps = tk.IntVar(value=50)
        ttk.Spinbox(controls, from_=10, to=100, increment=5, textvariable=self.steps).pack(fill='x')

        ttk.Label(controls, text='Seed').pack(anchor='w', pady=(12, 0))
        self.seed = tk.IntVar(value=42)
        ttk.Spinbox(controls, from_=0, to=999999, textvariable=self.seed).pack(fill='x')

        self.go_button = ttk.Button(controls, text='Generate 3D', command=self.start)
        self.go_button.pack(fill='x', pady=(20, 4))
        ttk.Button(controls, text='Open output folder', command=self.open_outputs).pack(fill='x')

        self.progress = ttk.Progressbar(controls, mode='indeterminate')
        self.progress.pack(fill='x', pady=(12, 0))
        self.status = ttk.Label(controls, text='Ready', wraplength=220)
        self.status.pack(fill='x', pady=(4, 0))

        self.preview = ttk.Label(root, text='Image preview', anchor='center', relief='groove')
        self.preview.pack(side='right', fill='both', expand=True, padx=12, pady=12)

    def choose_image(self):
        path = filedialog.askopenfilename(filetypes=[('Images', '*.png *.jpg *.jpeg *.webp *.bmp')])
        if path:
            self.image_path = path
            self.file_label.config(text=os.path.basename(path))
            self.show_preview(Image.open(path))

    def show_preview(self, image):
        image = image.copy()
        image.thumbnail((480, 480))
        self.preview_ref = ImageTk.PhotoImage(image)
        self.preview.config(image=self.preview_ref, text='')

    def set_status(self, text):
        self.root.after(0, lambda: self.status.config(text=text))

    def start(self):
        if not self.image_path:
            messagebox.showwarning('Idol', 'Choose an image first.')
            return
        self.go_button.config(state='disabled')
        self.progress.start(12)
        settings = dict(mode=self.mode.get(), num_gaussians=int(self.gaussians.get()),
                        steps=int(self.steps.get()), seed=int(self.seed.get()))
        threading.Thread(target=self.run, args=(self.image_path, settings, self.clean_bg.get()),
                         daemon=True).start()

    def run(self, path, settings, clean_bg):
        try:
            image = Image.open(path)
            if clean_bg:
                image = clean_fake_background(image)
            if self.pipeline is None:
                self.set_status('Loading model (first run downloads ~3 GB plus encoders)...')
                import torch
                from idol import IdolPipeline
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
                # torch.compile needs Triton, which isn't available on Windows
                self.pipeline = IdolPipeline.from_pretrained(device=device, optimize=False)
            self.set_status('Generating... this can take a few minutes.')
            start = time.time()
            output = self.pipeline(image, **settings)
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            name = os.path.splitext(os.path.basename(path))[0]
            out_path = os.path.join(OUTPUT_DIR, f'{name}-{settings["mode"]}-seed{settings["seed"]}-'
                                                f'{settings["num_gaussians"]}.ply')
            output.gaussian.save_ply(out_path)
            self.root.after(0, lambda: self.show_preview(output.preprocessed_image))
            self.set_status(f'Done in {time.time() - start:.0f}s. Saved:\n{out_path}')
        except Exception as e:
            msg = str(e)
            self.set_status('Failed.')
            self.root.after(0, lambda: messagebox.showerror('Idol', msg))
        finally:
            self.root.after(0, self.finish)

    def finish(self):
        self.progress.stop()
        self.go_button.config(state='normal')

    def open_outputs(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.startfile(OUTPUT_DIR)


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
