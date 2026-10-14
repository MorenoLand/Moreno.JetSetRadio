extends Screen
# The story scenes made of pictures (tools/comic.py): pages of a picture strip lying on a table, a camera that flies over
# each page and subtitles at the bottom between two black bars. A button skips the scene.

const FPS := 30.0
const TOP_BAR := 0.1467
const BOTTOM_BAR := 0.1867

var _scene: Dictionary = {}
var _model: Node3D
var _camera: Camera3D
var _page := 0
var _clock := 0.0
var _subtitle: BitmapText
var _done := false
var _language := "en"


func _ready() -> void:
	Sound.silence()
	var number := str(maxi(int(data.get("demo", 30)), 30) if int(data.get("demo", 30)) < 0 else int(data.get("demo", 30)))
	_scene = Assets.json("comic").get(number, {})
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.2, 0.2, 0.2)
	var world := WorldEnvironment.new()
	world.environment = env
	add_child(world)
	_model = Assets.model("models/comic_%s.glb" % number)
	if _model == null or _scene.is_empty():
		_finish()
		return
	add_child(_model)
	_camera = Camera3D.new()
	_camera.near = 0.05
	_camera.far = 200.0
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	add_child(_camera)
	_camera.current = true
	for bar in [[0.0, TOP_BAR, true], [1.0 - BOTTOM_BAR, BOTTOM_BAR, false]]:
		var rect := ColorRect.new()
		rect.color = Color.BLACK
		rect.set_anchors_preset(Control.PRESET_FULL_RECT)
		rect.anchor_top = bar[0]
		rect.anchor_bottom = bar[0] + bar[1]
		rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		root_control.add_child(rect)
		root_control.move_child(rect, 0)
	_subtitle = BitmapText.new()
	_subtitle.font = "font28"
	_subtitle.centered = true
	_subtitle.text_scale = 0.63
	_subtitle.pitch = 19.0
	_subtitle.position = Vector2(320.0, 393.0)
	canvas.add_child(_subtitle)
	_show_page(0)


func _show_page(index: int) -> void:
	_page = index
	_clock = 0.0
	var pages: Array = _scene["pages"]
	for i in pages.size():
		var node := _model.find_child(str(pages[i]["node"]), true, false)
		if node:
			node.visible = i == index


func _key_at(keys: Array, frame: float, size: int) -> Array:
	# keys are [frame, values...]; linear between them
	if keys.is_empty():
		return []
	var last := keys.size() - 1
	if frame <= float(keys[0][0]):
		return keys[0].slice(1, 1 + size)
	if frame >= float(keys[last][0]):
		return keys[last].slice(1, 1 + size)
	for i in last:
		var a: Array = keys[i]
		var b: Array = keys[i + 1]
		if frame >= float(a[0]) and frame <= float(b[0]):
			var span := maxf(float(b[0]) - float(a[0]), 1.0)
			var t := (frame - float(a[0])) / span
			var out: Array = []
			for k in size:
				out.append(lerpf(float(a[1 + k]), float(b[1 + k]), t))
			return out
	return keys[last].slice(1, 1 + size)


func _process(delta: float) -> void:
	if _done:
		return
	_clock += delta
	var frame := _clock * FPS
	var pages: Array = _scene["pages"]
	var page: Dictionary = pages[_page]
	if frame >= float(page["frames"]):
		if _page + 1 >= pages.size():
			_finish()
			return
		_show_page(_page + 1)
		return
	var p := _key_at(page["position"], frame, 3)
	var t := _key_at(page["target"], frame, 3)
	var fov := _key_at(page["fov"], frame, 1)
	if p.size() == 3 and t.size() == 3:
		_camera.position = Vector3(p[0], p[1], p[2])
		_camera.look_at(Vector3(t[0], t[1], t[2]), Vector3.UP)
	if fov.size() == 1:
		_camera.fov = Assets.vertical_fov(float(fov[0]))
	var text := ""
	for line in _scene.get("subtitles", []):
		if int(line["page"]) == _page and str(line["lang"]) == _language \
				and frame >= float(line["start"]) and frame < float(line["start"]) + float(line["frames"]):
			text = str(line["text"])
	_subtitle.text = text


func _finish() -> void:
	if _done:
		return
	_done = true
	finished.emit("loading", {"style": "bubble", "next": str(data.get("next", "garage")),
			"next_data": data.get("next_data", {})})


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("confirm") or event.is_action_pressed("back"):
		_finish()
