extends Node
# The flow of the game: title, garage, loading, stage. Each screen reports where to go next.
#
# Arguments after "--" for testing: --screen=NAME starts at a screen, --stage=N and --character=ID say what to load,
# --shot=PATH saves a screenshot after --wait=SECONDS (default 2) and quits, --keys=ACTION@SECONDS,... presses
# actions at those times (for example confirm@1.5,right@3), --hold=ACTION@SECONDS holds one from then on,
# --demo=N plays recorded demonstration N in the stage.

const SCREENS := {
	"intro": "res://scripts/screens/intro.gd",
	"title": "res://scripts/screens/title.gd",
	"slots": "res://scripts/screens/slots.gd",
	"cutscene": "res://scripts/screens/cutscene.gd",
	"pages": "res://scripts/screens/pages.gd",
	"garage": "res://scripts/screens/garage.gd",
	"loading": "res://scripts/screens/loading.gd",
	"stage": "res://scripts/game/stage.gd",
}

var _screen: Screen


func _ready() -> void:
	_register_input()
	add_child(Sound.new())
	# the small loading picture in the corner, above every screen
	var overlay := CanvasLayer.new()
	overlay.layer = 100
	overlay.add_child(CornerLoading.new())
	add_child(overlay)
	Screen.debug = OS.get_cmdline_user_args().has("--debug")
	var start := _argument("--screen=")
	var info := {"stage": _argument("--stage=") if _argument("--stage=") != "" else "1",
			"character": int(_argument("--character=")) if _argument("--character=") != "" else 0,
			"demo": int(_argument("--demo=")) if _argument("--demo=") != "" else -1}
	go(start if start != "" else "intro", info)
	for entry in _argument("--keys=").split(",", false):
		var parts := entry.split("@")
		if parts.size() == 2:
			_press_later(parts[0], float(parts[1]))
	for entry in _argument("--hold=").split(",", false):
		var parts := entry.split("@")
		if parts.size() == 2:
			_hold_later(parts[0], float(parts[1]))
	var shot := _argument("--shot=")
	if shot != "":
		var wait := float(_argument("--wait=")) if _argument("--wait=") != "" else 2.0
		await get_tree().create_timer(wait).timeout
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(shot)
		get_tree().quit()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_F1:
		Screen.debug = not Screen.debug
		if _screen:
			_screen.debug_changed()


func _hold_later(action: String, seconds: float) -> void:
	await get_tree().create_timer(seconds).timeout
	Input.action_press(action)


func _press_later(action: String, seconds: float) -> void:
	await get_tree().create_timer(seconds).timeout
	var down := InputEventAction.new()
	down.action = action
	down.pressed = true
	Input.parse_input_event(down)
	await get_tree().create_timer(0.1).timeout
	var up := InputEventAction.new()
	up.action = action
	up.pressed = false
	Input.parse_input_event(up)


func go(next: String, info: Dictionary) -> void:
	if _screen:
		_screen.queue_free()
		_screen = null
	if not SCREENS.has(next):
		push_warning("no screen " + next)
		return
	_screen = load(SCREENS[next]).new()
	_screen.data = info
	_screen.finished.connect(go)
	add_child(_screen)


func _argument(prefix: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(prefix):
			return a.substr(prefix.length())
	return ""


func _register_input() -> void:
	var keys := {
		"confirm": [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE],
		"back": [KEY_ESCAPE, KEY_BACKSPACE],
		"left": [KEY_LEFT, KEY_A],
		"right": [KEY_RIGHT, KEY_D],
		"up": [KEY_UP, KEY_W],
		"down": [KEY_DOWN, KEY_S],
		"jump": [KEY_SPACE],
		"boost": [KEY_SHIFT],
		"spray": [KEY_C, KEY_Z],
		"map": [KEY_M, KEY_TAB],
		"look_left": [KEY_Q],
		"look_right": [KEY_E],
		"look_up": [KEY_R],
		"look_down": [KEY_F],
	}
	var buttons := {
		"confirm": [JOY_BUTTON_A, JOY_BUTTON_START],
		"back": [JOY_BUTTON_B],
		"left": [JOY_BUTTON_DPAD_LEFT],
		"right": [JOY_BUTTON_DPAD_RIGHT],
		"up": [JOY_BUTTON_DPAD_UP],
		"down": [JOY_BUTTON_DPAD_DOWN],
		"jump": [JOY_BUTTON_A],
		"boost": [JOY_BUTTON_X],
		"spray": [JOY_BUTTON_RIGHT_SHOULDER],
		"map": [JOY_BUTTON_Y],
	}
	var axes := {
		"left": [[JOY_AXIS_LEFT_X, -1.0]], "right": [[JOY_AXIS_LEFT_X, 1.0]],
		"up": [[JOY_AXIS_LEFT_Y, -1.0]], "down": [[JOY_AXIS_LEFT_Y, 1.0]],
		"look_left": [[JOY_AXIS_RIGHT_X, -1.0]], "look_right": [[JOY_AXIS_RIGHT_X, 1.0]],
		"look_up": [[JOY_AXIS_RIGHT_Y, -1.0]], "look_down": [[JOY_AXIS_RIGHT_Y, 1.0]],
	}
	for action in keys:
		if not InputMap.has_action(action):
			InputMap.add_action(action, 0.3)
		for key in keys[action]:
			var e := InputEventKey.new()
			e.physical_keycode = key
			InputMap.action_add_event(action, e)
	for action in buttons:
		for b in buttons[action]:
			var e := InputEventJoypadButton.new()
			e.button_index = b
			InputMap.action_add_event(action, e)
	for action in axes:
		for a in axes[action]:
			var e := InputEventJoypadMotion.new()
			e.axis = a[0]
			e.axis_value = a[1]
			InputMap.action_add_event(action, e)
