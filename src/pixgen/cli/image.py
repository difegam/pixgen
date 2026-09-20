from cyclopts import App

image_app = App(name="image", help="Pixgen Image Generation")


@image_app.command
def create() -> None:
    print("Creating image...")


@image_app.command
def edit() -> None:
    print("Editing image...")
