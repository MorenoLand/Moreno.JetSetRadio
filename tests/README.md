# Tests

Run headless, with a timeout:

```
redot --headless --path . -s res://tests/smoke_boot.gd
```

`smoke_boot.gd` loads every script of the project, then `scenes/main.tscn`, and checks that the scene builds its UI. It prints
`smoke_boot: ok` and exits 0.

Screens can be checked by starting the game at one and saving a picture (see the README for the arguments):

```
redot --path . --minimized --audio-driver Dummy -- --screen=garage --shot=garage.png --wait=2
```
