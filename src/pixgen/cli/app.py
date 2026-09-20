from cyclopts import App

from pixgen.cli.image import image_app

app = App(name="pixgen", help="Pixgen Image Generation CLI")
app.command(image_app)


@app.default
def main() -> None: ...


@app.command
def info() -> None: ...


@app.command
def doctor() -> None: ...


if __name__ == "__main__":
    app()
