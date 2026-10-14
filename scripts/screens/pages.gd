extends Screen
# The lists behind the title menu: achievements, leaderboards, help and options, bonus. They use the texts of the
# PC release (assets/strings.json) in the menu font on the green picture.

var _page := "achievements"


func _ready() -> void:
	Sound.music("rock_m.ogg")
	_page = str(data.get("page", "achievements"))
	var ground := TextureRect.new()
	ground.texture = Assets.texture("images/BACKGROUND1.PNG")
	ground.set_anchors_preset(Control.PRESET_FULL_RECT)
	ground.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	ground.stretch_mode = TextureRect.STRETCH_SCALE
	ground.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root_control.add_child(ground)
	root_control.move_child(ground, 0)
	var strings: Array = Assets.json("strings").get("strings", [])
	var title := BitmapText.new()
	title.font = "title"
	title.text_scale = 0.5
	title.tint = Color(1.0, 0.25, 0.25)
	title.position = Vector2(34.0, 16.0)
	title.rotation = deg_to_rad(5.0)
	canvas.add_child(title)
	var lines: Array = []
	match _page:
		"achievements":
			title.text = _text(strings, 3)
			for i in range(31, 60):
				lines.append("%s  -  %s" % [_text(strings, i), _text(strings, i + 30)])
		"leaderboards":
			title.text = _text(strings, 4)
			lines.append(_text(strings, 119))
		"options":
			title.text = _text(strings, 5)
			for i in [167, 168, 169, 170, 176, 217]:
				lines.append(_text(strings, i))
		"bonus":
			title.text = _text(strings, 6)
			lines.append(_text(strings, 197))
	var y := 120.0
	for line in lines:
		var item := BitmapText.new()
		item.font = "regular16"
		item.text = line
		item.text_scale = 0.5
		item.tint = Color(1.0, 0.95, 0.2)
		item.position = Vector2(40.0, y)
		canvas.add_child(item)
		y += 14.0 if lines.size() > 12 else 26.0


func _text(strings: Array, index: int) -> String:
	if index < strings.size() and strings[index].size() > 0:
		return str(strings[index][0])
	return ""


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("back") or event.is_action_pressed("confirm"):
		finished.emit("title", {})
