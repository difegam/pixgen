from cyclopts import App

image_app = App(name="image", help="Pixgen Image Generation")


@image_app.command
def create() -> None: ...


@image_app.command
def edit() -> None: ...
