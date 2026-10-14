extends Screen
# Two loading screens. Going into a stage shows "now loading": the yellow figure and the rings, seen by a camera at the
# origin with the scene 80 units away; the stage and the character are read on a second thread while it plays. The
# other changes of screen (to the garage, ...) show the head with the speech bubble of the PC release on black.

const SHORTEST := 2.5
const BUBBLE_TIME := 1.6

var _thread: Thread
var _elapsed := 0.0
var _result: Dictionary = {}
var _done := false
var _sent := false
var _bubble := false


func _ready() -> void:
	Sound.silence()
	_bubble = str(data.get("style", "figure")) == "bubble"
	if _bubble:
		var ground := ColorRect.new()
		ground.color = Color.BLACK
		ground.set_anchors_preset(Control.PRESET_FULL_RECT)
		root_control.add_child(ground)
		root_control.move_child(ground, 0)
		var picture := TextureRect.new()
		picture.texture = Assets.texture("images/loading_EN.png")
		picture.stretch_mode = TextureRect.STRETCH_SCALE
		picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		picture.size = Vector2(340, 112)
		picture.position = Vector2(320.0 - 170.0, 240.0 - 56.0)
		canvas.add_child(picture)
		return
	var info := Assets.screen("loading")
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	# the loading task sets the clear colour 0xFF37640A (dark green) and puts black back when it ends
	env.background_color = Color8(0x37, 0x64, 0x0A)
	var world := WorldEnvironment.new()
	world.environment = env
	add_child(world)

	var holder := Node3D.new()
	holder.position = Vector3(0.0, 0.0, -float(info.get("distance", 80.0)))
	add_child(holder)
	var model := Assets.model("models/loading.glb")
	if model:
		holder.add_child(model)
		for tree in info.get("trees", []):
			if tree.get("animation") != null:
				Assets.play_in(model, str(tree["animation"]))
	var camera := Camera3D.new()
	camera.near = 0.1
	camera.far = 1000.0
	camera.keep_aspect = Camera3D.KEEP_HEIGHT
	camera.fov = Assets.vertical_fov(float(info.get("fov", 1.48)))
	add_child(camera)
	camera.current = true

	_thread = Thread.new()
	_thread.start(_load.bind(str(data.get("stage", "1")), int(data.get("character", 0))))


func _load(stage: String, character: int) -> Dictionary:
	var out := {}
	out["stage"] = Assets.model("models/stage%s.glb" % stage)
	if FileAccess.file_exists(Assets.path("models/stage%s_zones.glb" % stage)):
		out["zones"] = Assets.model("models/stage%s_zones.glb" % stage)
	var skaters: Array = Assets.json("skaters").get("skaters", [])
	for s in skaters:
		if int(s["id"]) == character:
			out["skater"] = Assets.model(str(s["file"]))
			out["name"] = s["name"]
	return out


func _process(delta: float) -> void:
	_elapsed += delta
	if _bubble:
		if not _sent and _elapsed >= BUBBLE_TIME:
			_sent = true
			finished.emit(str(data.get("next", "garage")), data.get("next_data", {}))
		return
	if not _done and _thread and not _thread.is_alive():
		_result = _thread.wait_to_finish()
		_thread = null
		_result["character"] = data.get("character", 0)
		_result["stage_id"] = data.get("stage", "1")
		_result["demo"] = data.get("demo", -1)
		_done = true
	if _done and not _sent and _elapsed >= SHORTEST:
		_sent = true
		finished.emit("stage", _result)


func _exit_tree() -> void:
	if _thread and _thread.is_started():
		_thread.wait_to_finish()
