extends Node3D
# Free-fly viewer for the exported stages.
#   WASD move, Q/E down/up, Shift fast, arrow keys or a held mouse button look.
#   number keys or [ ] switch stage, R reset the view, B backdrop, C double sided faces, T textures, F1 help.
# Arguments after "--" for the tests: --shot=PATH saves a screenshot and quits, --cam=px,py,pz,tx,ty,tz places the
# camera, --stage=N picks a stage by position in the list, --backdrop shows the backdrop, --double-sided and
# --untextured set those options.

const INDEX_PATH := "res://assets/index.json"
const HELP := "WASD move   Q/E down/up   Shift fast   arrows or mouse drag look\n" \
		+ "1-9 or [ ] stage   R reset   B backdrop   C double sided   T textures   F1 help"

var _camera: Camera3D
var _info: Label
var _help: Label
var _picker: OptionButton
var _models: Array = []
var _current := -1
var _model_root: Node = null
var _bounds := AABB()
var _yaw := 0.0
var _pitch := 0.0
var _speed := 20.0
var _double_sided := false
var _textured := true
var _backdrop := false
var _materials: Array = []
var _backdrop_nodes: Array = []


func _ready() -> void:
	_build_scene()
	_load_index()
	if _models.is_empty():
		_info.text = "No models found. Run tools/extract.py."
		return
	for m in _models:
		_picker.add_item(m.get("name", "model"))
	_backdrop = _has_argument("--backdrop")
	_double_sided = _has_argument("--double-sided")
	_textured = not _has_argument("--untextured")
	var first := int(_argument("--stage="))
	_show_model(first)
	var cam := _argument("--cam=")
	if cam != "":
		var v := cam.split_floats(",")
		if v.size() == 6:
			_camera.position = Vector3(v[0], v[1], v[2])
			_camera.look_at(Vector3(v[3], v[4], v[5]))
			_yaw = _camera.rotation.y
			_pitch = _camera.rotation.x
	var shot := _argument("--shot=")
	if shot != "":
		await get_tree().create_timer(1.0).timeout
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(shot)
		get_tree().quit()


func _has_argument(flag: String) -> bool:
	return OS.get_cmdline_user_args().has(flag)


func _argument(prefix: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(prefix):
			return a.substr(prefix.length())
	return ""


func _build_scene() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.55, 0.72, 0.95)
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	_camera = Camera3D.new()
	_camera.far = 20000.0
	_camera.near = 0.1
	add_child(_camera)

	var layer := CanvasLayer.new()
	add_child(layer)
	_info = _make_label(layer, Vector2(12, 8))
	_help = _make_label(layer, Vector2(12, 0))
	_help.text = HELP
	_help.anchor_top = 1.0
	_help.anchor_bottom = 1.0
	_help.offset_top = -52
	_picker = OptionButton.new()
	_picker.focus_mode = Control.FOCUS_NONE
	_picker.anchor_left = 1.0
	_picker.anchor_right = 1.0
	_picker.offset_left = -170
	_picker.offset_right = -12
	_picker.offset_top = 8
	_picker.item_selected.connect(_show_model)
	layer.add_child(_picker)


func _make_label(layer: CanvasLayer, at: Vector2) -> Label:
	var label := Label.new()
	label.position = at
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_color_override("font_color", Color.WHITE)
	label.add_theme_color_override("font_outline_color", Color.BLACK)
	label.add_theme_constant_override("outline_size", 4)
	layer.add_child(label)
	return label


func _load_index() -> void:
	if not FileAccess.file_exists(INDEX_PATH):
		return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(INDEX_PATH))
	if parsed is Dictionary:
		_models = parsed.get("models", [])


func _show_model(i: int) -> void:
	_current = (i + _models.size()) % _models.size()
	_picker.select(_current)
	if _model_root:
		_model_root.queue_free()
		_model_root = null
	var entry: Dictionary = _models[_current]
	var path := ProjectSettings.globalize_path("res://assets/" + entry["file"])
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_file(path, state)
	if err != OK:
		_info.text = "Could not read %s (error %d)" % [path, err]
		return
	_model_root = doc.generate_scene(state)
	add_child(_model_root)
	_materials.clear()
	var stack: Array = [_model_root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		stack.append_array(n.get_children())
		if n is MeshInstance3D:
			for s in n.mesh.get_surface_count():
				var m = n.mesh.surface_get_material(s)
				if m is BaseMaterial3D:
					_materials.append({"material": m, "texture": m.albedo_texture, "cull": m.cull_mode})
	_backdrop_nodes.clear()
	for child in _model_root.get_children():
		if str(child.name).begins_with("backdrop"):
			_backdrop_nodes.append(child)
			child.visible = _backdrop
	_bounds = _scene_bounds(_model_root, _backdrop_nodes)
	_apply_material_options()
	_reset_view()
	_update_info()


func _apply_material_options() -> void:
	for item in _materials:
		var m: BaseMaterial3D = item["material"]
		m.cull_mode = BaseMaterial3D.CULL_DISABLED if _double_sided else item["cull"]
		m.albedo_texture = item["texture"] if _textured else null


func _scene_bounds(node: Node, skip: Array) -> AABB:
	var box := AABB()
	var first := true
	var stack: Array = [node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if skip.has(n):
			continue
		for c in n.get_children():
			stack.append(c)
		if n is MeshInstance3D:
			var b: AABB = n.global_transform * n.get_aabb()
			box = b if first else box.merge(b)
			first = false
	return box


func _reset_view() -> void:
	var size := _bounds.size.length()
	_speed = maxf(size * 0.15, 2.0)
	var c := _bounds.get_center()
	_camera.position = c + Vector3(0.0, size * 0.25, size * 0.45)
	_camera.look_at(c)
	_yaw = _camera.rotation.y
	_pitch = _camera.rotation.x


func _update_info() -> void:
	var entry: Dictionary = _models[_current]
	_info.text = "%s   %d triangles" % [entry.get("name", "model"), int(entry.get("triangles", 0))]


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		if event.button_mask & (MOUSE_BUTTON_MASK_LEFT | MOUSE_BUTTON_MASK_RIGHT):
			_look(-event.relative.x * 0.003, -event.relative.y * 0.003)
	elif event is InputEventKey and event.pressed and not event.echo and not _models.is_empty():
		match event.keycode:
			KEY_BRACKETRIGHT:
				_show_model(_current + 1)
			KEY_BRACKETLEFT:
				_show_model(_current - 1)
			KEY_R:
				_reset_view()
			KEY_B:
				_backdrop = not _backdrop
				for node in _backdrop_nodes:
					node.visible = _backdrop
			KEY_C:
				_double_sided = not _double_sided
				_apply_material_options()
			KEY_T:
				_textured = not _textured
				_apply_material_options()
			KEY_F1:
				_help.visible = not _help.visible
			_:
				var n: int = event.keycode - KEY_1
				if n >= 0 and n < _models.size():
					_show_model(n)


func _look(dyaw: float, dpitch: float) -> void:
	_yaw += dyaw
	_pitch = clampf(_pitch + dpitch, -1.55, 1.55)
	_camera.rotation = Vector3(_pitch, _yaw, 0.0)


func _process(delta: float) -> void:
	if _models.is_empty():
		return
	var turn := Input.get_axis("ui_right", "ui_left") * 1.6 * delta
	var tilt := Input.get_axis("ui_down", "ui_up") * 1.2 * delta
	if turn != 0.0 or tilt != 0.0:
		_look(turn, tilt)
	var dir := Vector3.ZERO
	if Input.is_key_pressed(KEY_W):
		dir -= _camera.global_transform.basis.z
	if Input.is_key_pressed(KEY_S):
		dir += _camera.global_transform.basis.z
	if Input.is_key_pressed(KEY_A):
		dir -= _camera.global_transform.basis.x
	if Input.is_key_pressed(KEY_D):
		dir += _camera.global_transform.basis.x
	if Input.is_key_pressed(KEY_E):
		dir += Vector3.UP
	if Input.is_key_pressed(KEY_Q):
		dir -= Vector3.UP
	if dir != Vector3.ZERO:
		var fast := 4.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0
		_camera.position += dir.normalized() * _speed * fast * delta
