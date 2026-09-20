from __future__ import annotations

from cyclopts import App

from pixgen.cli.image import image_app

app = App(name="pixgen", help="Pixgen Image Generation CLI")
app.command(image_app)


@app.default
def main():
    print("Welcome to Pixgen CLI!")


@app.command
def info() -> None:
    print("pixgen version v0.1.0")


@app.command
def doctor() -> None:
    print("Running doctor checks...")


if __name__ == "__main__":
    app()
