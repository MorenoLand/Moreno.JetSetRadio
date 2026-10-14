extends Screen
# The garage: a room with the characters standing in it. The camera moves between them as the cursor moves, and a
# name plate shows who is selected. After the character comes the choice of the area.
#
# What stands where, which camera belongs to which character and how the characters are named comes from the game's
# own tables (tools/interface.py); the order of the cursor is the order of the characters' selection slots.

const PLAYABLE := 10
const DEFAULT_STAGE := "1"
const MOVE_TIME := 0.55
const FOV := 1.2387      # 12919 in the game's 65536-per-turn units: 71 degrees

# the choices of the area screen: label, stage, sheet, label rectangle in the 640 x 480 map picture
const AREAS := [
	{"label": "SHIBUYA-CHO", "stage": "1", "map": 0, "rect": Rect2(198, 326, 172, 30)},
	{"label": "BENTEN-CHO", "stage": "2", "map": 0, "rect": Rect2(8, 132, 160, 30)},
	{"label": "KOGANE-CHO", "stage": "3", "map": 0, "rect": Rect2(474, 229, 160, 30)},
	{"label": "BANTAM STREET", "stage": "5", "map": 4, "rect": Rect2(54, 252, 198, 30)},
	{"label": "GRIND SQUARE", "stage": "6", "map": 4, "rect": Rect2(426, 106, 180, 30)},
]

var _info: Dictionary
var _ring: Array = []            # character ids in cursor order
var _cursor := 0
var _camera: Camera3D
var _from_position := Vector3.ZERO
var _from_target := Vector3.ZERO
var _to_position := Vector3.ZERO
var _to_target := Vector3.ZERO
var _blend := 1.0
var _model: Node3D
var _idle_players := {}
var _plate: TextureRect
var _tag_left: TextureRect
var _tag_right: TextureRect
var _banner: TextureRect
var _mode := 0                   # 0 character, 1 area
var _area := 0
var _map: TextureRect
var _frame: ColorRect
var _area_label: Label
var _pulse := 0.0
var _plates: Array = []
var _tags: Array = []


func _ready() -> void:
	Sound.music("let_m.ogg")
	_info = Assets.screen("garage")
	var skaters: Dictionary = Assets.json("skaters")
	var list: Array = skaters.get("skaters", [])
	var characters: Array = _info.get("characters", [])
	var present := {}
	for c in characters:
		present[int(c["id"])] = c
	var ordered: Array = []
	for c in characters:
		if int(c["id"]) < PLAYABLE:
			ordered.append(c)
	ordered.sort_custom(func(a, b): return int(a["slot"]) < int(b["slot"]))
	for c in ordered:
		_ring.append(int(c["id"]))
	_build_room(characters)
	_build_ui()
	if data.has("character"):
		_cursor = maxi(_ring.find(int(data["character"])), 0)
	_go_to(_cursor, true)


func _build_room(characters: Array) -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.04, 0.05, 0.08)
	var world := WorldEnvironment.new()
	world.environment = env
	add_child(world)

	_model = Assets.model("models/garage.glb")
	if _model:
		add_child(_model)
		for c in characters:
			var id := int(c["id"])
			if not _ring.has(id):
				# the body of a character is one skinned mesh next to its joints
				var body := _model.find_child(str(c["node"]) + "_skin", true, false)
				if body:
					body.visible = false
				continue
			var idle: Array = c.get("idle", [])
			if idle.size() > 0:
				_idle_players[id] = Assets.play_in(_model, str(idle[0]["name"]))
	_camera = Camera3D.new()
	_camera.near = 0.5
	_camera.far = 3000.0
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.fov = Assets.vertical_fov(FOV)
	add_child(_camera)
	_camera.current = true
	light_scene(world.environment, _camera)


func _build_ui() -> void:
	_plates = _info.get("plates", [])
	_tags = _info.get("tags", [])
	_plate = sprite(_plates[_ring[0]])
	_tag_left = sprite(_tags[_ring[0]])
	_tag_right = sprite(_tags[_ring[0]])
	_tag_right.position.x = PICTURE.x - _tag_right.position.x - _tag_right.size.x
	# the banner is the one sprite of the first sheet that is as wide as 406 pixels and sits near the top
	for s in _info.get("sprites", []):
		if s["sheet"] == "ui/garage_1.png" and absf(s["w"] - 406.0) < 1.0 and s["y"] < 100.0:
			_banner = sprite(s)
			break

	_map = TextureRect.new()
	_map.visible = false
	_map.position = Vector2.ZERO
	_map.size = PICTURE
	_map.stretch_mode = TextureRect.STRETCH_SCALE
	_map.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	canvas.add_child(_map)
	_frame = ColorRect.new()
	_frame.color = Color(1.0, 0.9, 0.0, 0.35)
	_frame.visible = false
	canvas.add_child(_frame)
	_area_label = Label.new()
	_area_label.position = Vector2(0, 430)
	_area_label.size = Vector2(PICTURE.x, 30)
	_area_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_area_label.add_theme_font_size_override("font_size", 26)
	_area_label.add_theme_color_override("font_color", Color(1.0, 0.9, 0.0))
	_area_label.add_theme_color_override("font_outline_color", Color.BLACK)
	_area_label.add_theme_constant_override("outline_size", 6)
	_area_label.visible = false
	canvas.add_child(_area_label)


func _slot_camera(id: int) -> Array:
	for c in _info["characters"]:
		if int(c["id"]) == id:
			var cam: Dictionary = _info["cameras"][int(c["slot"])]
			var p: Array = cam["position"]
			var t: Array = cam["target"]
			return [Vector3(p[0], p[1], p[2]), Vector3(t[0], t[1], t[2])]
	return [Vector3.ZERO, Vector3.FORWARD]


func _go_to(index: int, immediate: bool = false) -> void:
	_cursor = (index + _ring.size()) % _ring.size()
	var id: int = _ring[_cursor]
	var cam := _slot_camera(id)
	_from_position = _camera.position if not immediate else cam[0]
	_from_target = _camera_target() if not immediate else cam[1]
	_to_position = cam[0]
	_to_target = cam[1]
	_blend = 1.0 if immediate else 0.0
	var left: int = _ring[(_cursor - 1 + _ring.size()) % _ring.size()]
	var right: int = _ring[(_cursor + 1) % _ring.size()]
	_set_sprite(_plate, _plates[id])
	_set_sprite(_tag_left, _tags[left])
	_set_sprite(_tag_right, _tags[right])
	_tag_right.position.x = PICTURE.x - _tags[right]["x"] - _tags[right]["w"]
	if immediate:
		_place_camera(1.0)


func _set_sprite(rect: TextureRect, info: Dictionary) -> void:
	var sheet := Assets.texture(str(info["sheet"]))
	var uv: Array = info["uv"]
	var atlas := AtlasTexture.new()
	atlas.atlas = sheet
	atlas.region = Rect2(uv[0] * sheet.get_width(), uv[1] * sheet.get_height(),
			(uv[2] - uv[0]) * sheet.get_width(), (uv[3] - uv[1]) * sheet.get_height())
	rect.texture = atlas
	rect.position = Vector2(info["x"], info["y"])
	rect.size = Vector2(info["w"], info["h"])


var _look := Vector3.ZERO


func _camera_target() -> Vector3:
	return _look


func _place_camera(t: float) -> void:
	var e := t * t * (3.0 - 2.0 * t)
	_camera.position = _from_position.lerp(_to_position, e)
	_look = _from_target.lerp(_to_target, e)
	_camera.look_at(_look)


func _process(delta: float) -> void:
	if _blend < 1.0:
		_blend = minf(_blend + delta / MOVE_TIME, 1.0)
		_place_camera(_blend)
	_pulse += delta
	if _mode == 1:
		_frame.color.a = 0.25 + 0.2 * sin(_pulse * 6.0)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_echo():
		return
	if _mode == 0:
		if event.is_action_pressed("right"):
			Sound.sfx(Sound.MOVE)
			_go_to(_cursor + 1)
		elif event.is_action_pressed("left"):
			Sound.sfx(Sound.MOVE)
			_go_to(_cursor - 1)
		elif event.is_action_pressed("map"):
			# the choice of the area (M, Tab or Y); confirm alone starts at the first stage
			Sound.sfx(Sound.CONFIRM)
			_enter_area_screen()
		elif event.is_action_pressed("confirm"):
			if Screen.debug:
				Sound.sfx(Sound.CONFIRM)
				_enter_area_screen()
			else:
				Sound.sfx(Sound.START)
				finished.emit("loading", {"character": _ring[_cursor], "stage": DEFAULT_STAGE})
		elif event.is_action_pressed("back"):
			Sound.sfx(Sound.BACK)
			finished.emit("title", {})
	else:
		if event.is_action_pressed("right") or event.is_action_pressed("down"):
			Sound.sfx(Sound.MOVE)
			_choose_area(_area + 1)
		elif event.is_action_pressed("left") or event.is_action_pressed("up"):
			Sound.sfx(Sound.MOVE)
			_choose_area(_area - 1)
		elif event.is_action_pressed("confirm"):
			Sound.sfx(Sound.START)
			finished.emit("loading", {"character": _ring[_cursor], "stage": AREAS[_area]["stage"]})
		elif event.is_action_pressed("back"):
			Sound.sfx(Sound.BACK)
			_leave_area_screen()


func _enter_area_screen() -> void:
	_mode = 1
	_plate.visible = false
	_tag_left.visible = false
	_tag_right.visible = false
	if _banner:
		_banner.visible = false
	_map.visible = true
	_frame.visible = true
	_area_label.visible = true
	_choose_area(_area)


func _leave_area_screen() -> void:
	_mode = 0
	_plate.visible = true
	_tag_left.visible = true
	_tag_right.visible = true
	if _banner:
		_banner.visible = true
	_map.visible = false
	_frame.visible = false
	_area_label.visible = false


func _choose_area(index: int) -> void:
	_area = (index + AREAS.size()) % AREAS.size()
	var a: Dictionary = AREAS[_area]
	var sheet := Assets.texture(str(_info["sheets"][str(a["map"])]))
	var atlas := AtlasTexture.new()
	atlas.atlas = sheet
	atlas.region = Rect2(0, 0, 640, 480)
	_map.texture = atlas
	var r: Rect2 = a["rect"]
	_frame.position = r.position
	_frame.size = r.size
	_area_label.text = a["label"]
