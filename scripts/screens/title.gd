extends Screen
# Title screen: the 3D logo assembles itself, then "press start" and a three-way menu.
#
# The 3D scene is four object trees with their motions (260 frames) seen by a fixed camera; the game draws them in
# front of the camera, scaled down, so the same transform is used here (see docs/screens.md).

const FPS := 30.0
const ITEMS := ["NEW GAME", "LOAD", "TUTORIAL", "ACHIEVEMENTS", "LEADERBOARDS", "HELP & OPTIONS", "BONUS", "EXIT GAME"]
const ITEM_TOP := 203.0
const ITEM_PITCH := 26.7
const LAST_FRAME := 259
const FULL_POSITION := Vector3(-10.6, 28.15, 600.0)
const FULL_SCALE := 0.017
const MENU_POSITION := Vector3(-10.6, 30.15, 600.0)
const MENU_SCALE := 0.0085

enum Phase { INTRO, WAIT, MENU }

var _phase := Phase.INTRO
var _clock := 0.0
var _holder: Node3D
var _model: Node3D
var _players: Array = []
var _trees: Array = []        # the nodes of the four trees
var _press_start: TextureRect
var _items: Array = []        # the texts of the menu
var _cursor: TextureRect
var _background: SubViewport      # the demonstration of the game that plays behind the logo
var _logo_view: SubViewport
var _loader: Thread
var _choice := 0
var _arrows: Array = []
var _blink := 0.0
var _mix := 0.0               # 0 = logo as in the intro, 1 = logo as in the menu


func _ready() -> void:
	Sound.music("rock_m.ogg")
	var info := Assets.screen("title")
	_make_views()
	_build_3d(info)
	_build_2d(info)
	_apply_mix()


func _make_views() -> void:
	# behind: the game's own demonstration; in front of it: the logo, drawn with a clear background
	var back := SubViewportContainer.new()
	back.stretch = true
	back.set_anchors_preset(Control.PRESET_FULL_RECT)
	back.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_background = SubViewport.new()
	_background.handle_input_locally = false
	back.add_child(_background)
	layer.add_child(back)
	layer.move_child(back, 0)
	var front := SubViewportContainer.new()
	front.stretch = true
	front.set_anchors_preset(Control.PRESET_FULL_RECT)
	front.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_logo_view = SubViewport.new()
	_logo_view.transparent_bg = true
	_logo_view.own_world_3d = true
	front.add_child(_logo_view)
	layer.add_child(front)
	layer.move_child(front, 1)
	_loader = Thread.new()
	_loader.start(_load_demo_stage)
	CornerLoading.active = true


func _load_demo_stage() -> Dictionary:
	var out := {"stage": Assets.model("models/stage1.glb"), "background": true, "stage_id": "1", "character": 0,
			"demo": 0}
	if FileAccess.file_exists(Assets.path("models/stage1_zones.glb")):
		out["zones"] = Assets.model("models/stage1_zones.glb")
	for s in Assets.json("skaters").get("skaters", []):
		if int(s["id"]) == 0:
			out["skater"] = Assets.model(str(s["file"]))
	return out


func _exit_tree() -> void:
	CornerLoading.active = false
	if _loader and _loader.is_started():
		_loader.wait_to_finish()


func _build_3d(info: Dictionary) -> void:
	_holder = Node3D.new()
	_logo_view.add_child(_holder)
	_model = Assets.model("models/title.glb")
	if _model:
		_holder.add_child(_model)
		for tree in info.get("trees", []):
			var node := _model.find_child(str(tree["node"]), true, false)
			var skin := _model.find_child(str(tree["node"]) + "_skin", true, false)
			_trees.append(skin if skin else node)
			if tree.get("animation") != null:
				var p := Assets.play_in(_model, str(tree["animation"]), false)
				if p:
					_players.append(p)

	var camera_info: Dictionary = info.get("camera", {})
	var camera := Camera3D.new()
	camera.near = 0.1
	camera.far = 4000.0
	camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_logo_view.add_child(camera)
	var p0: Array = camera_info["position"][0]
	var t0: Array = camera_info["target"][0]
	camera.position = Vector3(p0[0], p0[1], p0[2])
	camera.look_at(Vector3(t0[0], t0[1], t0[2]))
	camera.fov = Assets.vertical_fov(camera_info["fov"][0])
	camera.current = true


func _build_2d(info: Dictionary) -> void:
	var by_place := {}
	for s in info.get("sprites", []):
		by_place["%d,%d" % [int(s["x"]), int(s["y"])]] = s
	_press_start = sprite(by_place["195,245"])
	_press_start.position.y = 362.0          # below the full-size logo
	_press_start.visible = false
	var names: Array = []
	var listed: Array = Assets.json("strings").get("strings", [])
	var from_file := {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 8}
	for n in ITEMS.size():
		var label := str(ITEMS[n])
		var at: int = from_file[n]
		if at < listed.size() and listed[at].size() > 0 and str(listed[at][0]) != "":
			label = str(listed[at][0])
		names.append(label)
	for n in names.size():
		var item := BitmapText.new()
		item.font = "mainmenu"
		item.text = names[n]
		item.text_scale = 0.46
		item.centered = true
		item.position = Vector2(320.0, ITEM_TOP + n * ITEM_PITCH)
		item.visible = false
		canvas.add_child(item)
		_items.append(item)
	_cursor = TextureRect.new()
	_cursor.texture = Assets.texture("images/sprayy.png")
	_cursor.stretch_mode = TextureRect.STRETCH_SCALE
	_cursor.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_cursor.size = Vector2(12, 24)
	_cursor.visible = false
	canvas.add_child(_cursor)
	_add_copyright(str(by_place["195,245"]["sheet"]))


func _add_copyright(sheet_file: String) -> void:
	# two lines of small print that are part of the same sheet as the menu texts
	var sheet := Assets.texture(sheet_file)
	if sheet == null:
		return
	var lines := [Rect2(0, 418, 410, 44), Rect2(50, 470, 220, 35)]
	var y := 430.0
	for r in lines:
		var atlas := AtlasTexture.new()
		atlas.atlas = sheet
		atlas.region = r
		var rect := TextureRect.new()
		rect.texture = atlas
		rect.stretch_mode = TextureRect.STRETCH_SCALE
		rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		rect.size = r.size * 0.55
		rect.position = Vector2(320.0 - rect.size.x * 0.5, y)
		rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		canvas.add_child(rect)
		y += rect.size.y + 2.0


func _process(delta: float) -> void:
	_clock += delta
	if _loader and _loader.is_started() and not _loader.is_alive():
		var built: Dictionary = _loader.wait_to_finish()
		CornerLoading.active = false
		if built.get("stage") != null:
			var stage: Screen = load("res://scripts/game/stage.gd").new()
			stage.data = built
			_background.add_child(stage)
	match _phase:
		Phase.INTRO:
			if _clock * FPS >= LAST_FRAME:
				_phase = Phase.WAIT
				_clock = 0.0
		Phase.WAIT:
			_blink += delta
			_press_start.visible = true
			_press_start.modulate.a = 0.5 + 0.5 * absf(sin(_blink * 3.0))
			_mix = maxf(_mix - delta * 2.0, 0.0)
			_apply_mix()
		Phase.MENU:
			_press_start.visible = false
			_mix = minf(_mix + delta * 2.0, 1.0)
			_apply_mix()


func _apply_mix() -> void:
	# in the menu only the logo tree is drawn
	for i in range(1, _trees.size()):
		_trees[i].visible = _mix < 0.01
	var t := _mix * _mix * (3.0 - 2.0 * _mix)
	_holder.position = FULL_POSITION.lerp(MENU_POSITION, t)
	_holder.scale = Vector3.ONE * lerpf(FULL_SCALE, MENU_SCALE, t)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_echo():
		return
	if event.is_action_pressed("confirm"):
		match _phase:
			Phase.INTRO:
				_skip_intro()
			Phase.WAIT:
				_phase = Phase.MENU
				Sound.call_voice(0)      # the DJ calls the station: the first voice stream the game keeps
				_show_menu()
			Phase.MENU:
				_choose()
	elif _phase == Phase.MENU:
		if event.is_action_pressed("up"):
			_select(_choice - 1)
		elif event.is_action_pressed("down"):
			_select(_choice + 1)
		elif event.is_action_pressed("back"):
			_phase = Phase.WAIT
			for item in _items:
				item.visible = false
			_cursor.visible = false


func _skip_intro() -> void:
	for p in _players:
		p.seek(LAST_FRAME / FPS, true)
	_clock = LAST_FRAME / FPS
	_phase = Phase.WAIT
	_clock = 0.0


func _show_menu() -> void:
	for item in _items:
		item.visible = true
	_cursor.visible = true
	_select(_choice, false)


func _select(index: int, sound: bool = true) -> void:
	if sound:
		Sound.sfx(Sound.MOVE)
	_choice = (index + _items.size()) % _items.size()
	for i in _items.size():
		_items[i].tint = Color(1.0, 0.92, 0.1) if i == _choice else Color(0.62, 0.58, 0.1, 0.85)
	var chosen: BitmapText = _items[_choice]
	_cursor.position = Vector2(320.0 - chosen.width_of(chosen.text) * 0.5 - 22.0, chosen.position.y - 3.0)


func _choose() -> void:
	Sound.sfx(Sound.CONFIRM)
	match _choice:
		0:
			finished.emit("slots", {"mode": "new"})
		1:
			finished.emit("slots", {"mode": "load"})
		2:
			finished.emit("garage", {"tutorial": true})
		3:
			finished.emit("pages", {"page": "achievements"})
		4:
			finished.emit("pages", {"page": "leaderboards"})
		5:
			finished.emit("pages", {"page": "options"})
		6:
			finished.emit("pages", {"page": "bonus"})
		7:
			get_tree().quit()
