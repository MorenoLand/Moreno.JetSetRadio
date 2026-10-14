extends Screen
# NEW GAME / LOAD: ten save slots on the green zigzag picture. The title of the screen is set in the large menu font, red
# and tilted; the bottom bar names the two buttons.

const SLOTS := 10
const TOP := 164.0
const PITCH := 26.7

var _marks: Array = []
var _choice := 0


func _ready() -> void:
	Sound.music("rock_m.ogg")
	var ground := TextureRect.new()
	ground.texture = Assets.texture("images/BACKGROUND1.PNG")
	ground.set_anchors_preset(Control.PRESET_FULL_RECT)
	ground.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	ground.stretch_mode = TextureRect.STRETCH_SCALE
	ground.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root_control.add_child(ground)
	root_control.move_child(ground, 0)

	var title := BitmapText.new()
	title.font = "title"
	title.text = "LOAD" if str(data.get("mode", "new")) == "load" else "NEW GAME"
	title.text_scale = 0.74
	title.tint = Color(1.0, 0.25, 0.25)
	title.position = Vector2(10.0, 40.0)
	title.rotation = deg_to_rad(8.0)
	canvas.add_child(title)

	for i in SLOTS:
		var mark := Control.new()
		mark.position = Vector2(320.0, TOP + i * PITCH)
		for k in 3:
			var bit := ColorRect.new()
			bit.size = Vector2(5, 2)
			bit.position = Vector2(-9.0 + k * 7.0, 0.0)
			bit.mouse_filter = Control.MOUSE_FILTER_IGNORE
			mark.add_child(bit)
		canvas.add_child(mark)
		_marks.append(mark)
	_select(0, false)

	# the bar at the bottom of the window
	var bar := ColorRect.new()
	bar.color = Color(0.0, 0.0, 0.0, 0.45)
	bar.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	bar.anchor_top = 0.896
	bar.anchor_bottom = 0.938
	bar.offset_top = 0.0
	bar.offset_bottom = 0.0
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root_control.add_child(bar)
	_button(bar, "images/button_a.png", "SELECT", 0.19)
	_button(bar, "images/button_b.png", "BACK", 0.71)


func _button(bar: Control, icon_file: String, label: String, at: float) -> void:
	var icon := TextureRect.new()
	icon.texture = Assets.texture(icon_file)
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.anchor_left = at
	icon.anchor_right = at
	icon.anchor_top = 0.0
	icon.anchor_bottom = 1.0
	icon.offset_left = 0.0
	icon.offset_right = 26.0
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bar.add_child(icon)
	var text := BitmapText.new()
	text.font = "mainmenu"
	text.text = label
	text.text_scale = 0.5
	text.anchor_left = at
	text.anchor_right = at
	text.anchor_top = 0.0
	text.offset_left = 30.0
	text.offset_top = 1.0
	bar.add_child(text)


func _select(index: int, sound: bool = true) -> void:
	if sound:
		Sound.sfx(Sound.MOVE)
	_choice = (index + SLOTS) % SLOTS
	for i in SLOTS:
		var on := i == _choice
		var mark: Control = _marks[i]
		mark.scale = Vector2(1.25, 1.5) if on else Vector2.ONE
		for bit in mark.get_children():
			(bit as ColorRect).color = Color(1.0, 0.95, 0.0) if on else Color(0.85, 0.85, 0.1, 0.85)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_echo():
		return
	if event.is_action_pressed("up"):
		_select(_choice - 1)
	elif event.is_action_pressed("down"):
		_select(_choice + 1)
	elif event.is_action_pressed("back"):
		Sound.sfx(Sound.BACK)
		finished.emit("title", {})
	elif event.is_action_pressed("confirm"):
		Sound.sfx(Sound.CONFIRM)
		if str(data.get("mode", "new")) == "load":
			finished.emit("loading", {"style": "bubble", "next": "garage", "next_data": {"load": true, "slot": _choice}})
		else:
			# a new game starts with the story: the picture strip of the opening, then the garage
			finished.emit("cutscene", {"demo": 30, "next": "garage", "next_data": {"slot": _choice}})
