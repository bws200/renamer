from photo_renamer.app import ImageProcessorApp


if __name__ == "__main__":
    import tkinter as tk

    root = tk.Tk()
    app = ImageProcessorApp(root)
    root.mainloop()
