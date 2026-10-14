extends Screen
# A stage with the chosen character skating in it.
#
# Ground and walls are the stage's own triangles, seen from both sides (without the cut-out leaves of trees). The game's
# collision is not decoded: the volume chunks of the stage data turned out to be zones, not walls (F1 shows them).
# The controls are an approximation: the original's physics are not decoded.

const MAX_SPEED := 111.1              # the game's 1.852 a frame at 60 frames a second (character block +0x48)
const BOOST_SPEED := 150.0            # 2.5 a frame (+0x4C)
const ACCELERATION := 1.8             # the speed closes 3 percent of the gap to the target each frame (+0x64 / +0x68)
const BOOST_ACCELERATION := 5.4       # three times that while boosting (shared block +0xEC)
const COAST := 1.8                    # letting go of the stick closes the gap to zero the same way
const BRAKE := 150.0
const GRIP := 10.0
const AIR_GRIP := 1.2
const TURN_RATE := 10.47              # 10 degrees a frame at 60 frames a second, in radians a second
const TIME_LIMIT := 60.0             # the countdown of the HUD
const GRAVITY := 377.8               # the take-off lifts 17 units in 18 frames (character block +0xC0, +0xC4 * +0xDC): speed falls linearly to zero
const JUMP_SPEED := 113.3
const COYOTE_TIME := 0.1
const JUMP_BUFFER := 0.12
const KNOCK_DOWN_SPEED := 70.0
const SLOPE_PULL := 110.0
const GRIND_RADIUS := 5.0
const GRIND_SPEED := 45.0
const CAN_RADIUS := [5.0, 7.5]            # pickup spheres of the small and the large can
const CAN_RESPAWN := 60.0                 # seconds until a small can is back
const CAN_VIEW := 900.0
const BODY_HEIGHT := 10.0
const BODY_RADIUS := 2.2
const BODY_TALL := 14.0
const STEP := 2.2
const CAMERA_DISTANCE := 42.0
const CAMERA_HEIGHT := 16.0
const CAMERA_FOLLOW := 1.8
const BOUNDS_MARGIN := 60.0
const SKY_SCALE := 4.0

# Motion numbers of the character files. The game's motions come in pairs of which the second has the whole
# figure turned half way round (skating backwards); those without the turn face the way the figure moves. Many of
# them are not loops: they carry the skater into a pose that the game then holds, so those play once and stay on
# their last frame (the numbers say which, measured by how far the last frame is from the first). Which motion is
# for what was picked by looking at them, the game's own table was not found (docs/formats.md).
# Motion numbers of the character's motion list as the player code sets them (x86 `FUN_004EDFF0`, `FUN_004ED700`,
# `FUN_004E7B50`): 0 standing, 2 and then 3 after 180 and 360 frames of standing, 4 rolling with no stick, 6 skating,
# 7 skating with the boost held, 11 braking, 96 and 97 take-off and air, landing 16 / 13 / 12 / 14 by the speed.
const MOTION_IDLE := 0
const MOTION_BORED := [2, 3]
const MOTION_COAST := 4
const MOTION_SKATE := 6
const MOTION_BOOST := 7
const MOTION_BRAKE := 11
const MOTION_GRIND := 128                     # earlier guess; the PC code uses 128 to 131 for spraying, not found for grinding
const MOTION_JUMP := 96
const MOTION_AIR := 97
const MOTION_FALL_LIGHT := 13
const MOTION_FALL_HARD := 14

var _world: Node3D
var _stage_nodes: Array = []
var _sky: Array = []
var _zone_nodes: Array = []
var _body: CharacterBody3D
var _model: Node3D
var _player: AnimationPlayer
var _camera: Camera3D
var _speed := 0.0
var _flat := Vector3.ZERO          # horizontal velocity, follows heading * speed with some slip
var _heading := 0.0
var _lean := 0.0
var _camera_yaw := 0.0
var _camera_pitch := 0.28
var _coyote := 0.0
var _jump_buffer := 0.0
var _air_time := 0.0
var _fallen := 0.0                 # seconds left of a fall
var _oneshot := 0.0                # seconds left of a motion that plays through (landing, idle gesture)
var _idle_time := 0.0
var _next_gesture := 6.0
var _since_change := 0.0
var _hud: Label
var _blocker := ""                 # what the skater last ran into (shown with F1)
var _effects: Array = []           # sound test: every effect file, stepped through with , and . (F1)
var _effect_labels: Array = []     # what the sound test shows for each of them
var _effect_index := -1
var _demo: Dictionary = {}          # a recorded demonstration that plays instead of the pad (attract mode)
var _demo_at := 0                  # record being held
var _demo_left := 0                # frames left of it
var _demo_jump := false
var _demo_clock := 0.0
var _se_jump := ""                  # the character's sounds, picked as the player code does (see _bank_sound)
var _se_land := ""
var _se_fall := ""
var _was_boosting := false
var _floor_vy := 0.0               # vertical speed of the last frame on the ground (ramps launch)
var _was_grounded := false
var _rails: Array = []             # polylines of grindable rails: PackedVector3Array each (the data has none yet)
var _cans: Array = []              # {node, pos, radius, kind, wait, grow}
var _can_count := 0
var _item_count := 0
var _can_label: Label
var _hud_view: Hud
var _cars: Array = []              # parked vehicles (static)
var _traffic_templates := {}       # vehicle type -> the mesh instance of the stage file that is copied per car
var _traffic: Array = []           # driving vehicles: {node, route, frame, speed}
var _traffic_clock := 0.0
var _spots: Array = []             # graffiti spots: {data, node, decal, tagged, centre, yaw}
var _tag: Dictionary = {}          # the spot being sprayed
var _cans_left := 0                # spray cans carried (the game starts a mission with none unless a flag is set)
var _tag_hint: BitmapText
var _props: Array = []             # poles and cones the skater can knock: {node, rest, cone, state, t, dir, amp}
var _clock_left := TIME_LIMIT
var _points_view: MeshInstance3D
var _rail_view: MeshInstance3D
var _grinding := false
var _g_rail := 0
var _g_seg := 0
var _g_t := 0.0
var _g_dir := 1
var _g_cool := 0.0
var _current_motion := -1
var _debug_motion := -1
var _bounds := AABB()
var _start := Vector3.ZERO
var _started := false
var _trace := OS.get_cmdline_user_args().has("--trace")
var _background := false          # played behind the title screen: no sound, no HUD, no input, the demonstration repeats


func _sfx(name: String) -> void:
	if not _background:
		Sound.sfx(name)


func _ready() -> void:
	_background = bool(data.get("background", false))
	var audio: Dictionary = Assets.json("audio")
	if not _background:
		Sound.playlist(audio.get("playlist", []))
	_add_bank_sounds()
	_se_jump = _bank_sound(9)
	_se_land = _bank_sound(12)
	_se_fall = _bank_sound(11)
	for entry in audio.get("sounds", []):
		_effects.append(entry["name"])
		_effect_labels.append(entry["name"])
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.56, 0.74, 0.95)
	var world := WorldEnvironment.new()
	world.environment = env
	add_child(world)

	_world = data.get("stage") as Node3D
	if _world:
		add_child(_world)
		_collect_stage(_world)
	# the zone volumes of the stage data: not solid, only drawn with F1
	var zones := data.get("zones") as Node3D
	if zones:
		add_child(zones)
		_collect_zones(zones)

	_body = CharacterBody3D.new()
	_body.floor_snap_length = 4.0
	_body.floor_max_angle = deg_to_rad(46.0)
	_body.floor_stop_on_slope = true
	_body.floor_constant_speed = true
	_body.safe_margin = 0.05
	var capsule := CapsuleShape3D.new()
	capsule.radius = BODY_RADIUS
	capsule.height = BODY_TALL
	var shape := CollisionShape3D.new()
	shape.shape = capsule
	shape.position = Vector3(0.0, BODY_TALL * 0.5, 0.0)
	_body.add_child(shape)
	add_child(_body)
	_model = data.get("skater") as Node3D
	if _model:
		_body.add_child(_model)
		_player = Assets.player_of(_model)

	_camera = Camera3D.new()
	_camera.near = 0.5
	_camera.far = 24000.0
	_camera.fov = 70.0
	add_child(_camera)
	_camera.current = true
	light_scene(env, _camera)

	_hud = Label.new()
	_hud.position = Vector2(12, 48)
	_hud.add_theme_color_override("font_color", Color.WHITE)
	_hud.add_theme_color_override("font_outline_color", Color.BLACK)
	_hud.add_theme_constant_override("outline_size", 4)
	_hud.visible = Screen.debug
	layer.add_child(_hud)

	_can_label = Label.new()
	_can_label.position = Vector2(12, 8)
	_can_label.add_theme_color_override("font_color", Color(1.0, 0.9, 0.1))
	_can_label.add_theme_color_override("font_outline_color", Color.BLACK)
	_can_label.add_theme_constant_override("outline_size", 4)
	_can_label.add_theme_font_size_override("font_size", 28)
	_can_label.visible = false
	layer.add_child(_can_label)
	_hud_view = Hud.new()
	layer.add_child(_hud_view)
	_tag_hint = BitmapText.new()
	_tag_hint.font = "mainmenu"
	_tag_hint.text = "SPRAY"
	_tag_hint.text_scale = 0.6
	_tag_hint.tint = Color(1.0, 0.92, 0.1)
	_tag_hint.visible = false
	canvas.add_child(_tag_hint)
	_tag_hint.position = Vector2(290.0, 340.0)
	if _background:
		layer.visible = false
		set_process_unhandled_input(false)
	_load_demo()
	_load_rails()
	_load_cans()
	_load_points()
	_load_spots()
	_load_traffic()
	await get_tree().physics_frame
	await get_tree().physics_frame
	_spawn()


func _add_bank_sounds() -> void:
	# the sounds of the common bank and of this character's two banks, for the sound test
	var listing: Dictionary = Assets.json("audio/sfx")
	var members: Array = [listing.get("common", -1)]
	var characters: Array = listing.get("characters", [])
	var id := int(data.get("character", 0))
	if id >= 0 and id < characters.size():
		members.append(characters[id]["voice"])
		members.append(characters[id]["effects"])
	var shown := {}
	for member in members:
		for sound in listing.get("sounds", []):
			if shown.has(sound["file"]):
				continue
			for use in sound["uses"]:
				if int(use[0]) == int(member):
					shown[sound["file"]] = true
					_effects.append("sfx/" + sound["file"])
					_effect_labels.append("bank %d sound %d  %.2f s%s" % [use[0], use[1], sound["seconds"],
							"  loops" if sound["looping"] else ""])
					break


func _bank_sound(index: int) -> String:
	# sound `index` of the character: the player code asks for (character, number); 9 is in the shared part of the
	# character's banks, 11 and 12 are lines of the voice bank
	var listing: Dictionary = Assets.json("audio/sfx")
	var characters: Array = listing.get("characters", [])
	var id := int(data.get("character", 0))
	if id < 0 or id >= characters.size():
		return ""
	for member in [characters[id]["voice"], characters[id]["effects"]]:
		for sound in listing.get("sounds", []):
			for use in sound["uses"]:
				if int(use[0]) == int(member) and int(use[1]) == index:
					return "sfx/" + sound["file"]
	return ""


func _collect_stage(node: Node) -> void:
	var stack: Array = [node]
	var foliage := {}
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		stack.append_array(n.get_children())
		if n.get_parent() != null and str(n.get_parent().name).begins_with("prop_"):
			pass
		elif n is MeshInstance3D and str(n.name).begins_with("traffic_"):
			n.visible = false
			_traffic_templates[int(str(n.name).substr(8))] = n
		elif n is MeshInstance3D and str(n.name).begins_with("car_"):
			_make_car(n as MeshInstance3D)
		elif n is Node3D and str(n.name).begins_with("prop_"):
			_props.append({"node": n, "rest": (n as Node3D).global_transform, "cone": str(n.name).begins_with("prop_cone"),
					"tilt": n.find_child("tilt", false, false), "state": 0, "frame": 0.0, "v": Vector3.ZERO,
					"spin": Vector3.ZERO, "euler": Vector3.ZERO, "clock": 0.0})
		elif n is MeshInstance3D and str(n.name).begins_with("backdrop"):
			_make_sky(n)
		elif n is MeshInstance3D:
			# one solid per surface: the leaves of trees are cut-out cards that nothing should bump into
			for surface in n.mesh.get_surface_count():
				var material: Material = n.mesh.surface_get_material(surface)
				if not foliage.has(material):
					foliage[material] = _is_foliage(material)
				if foliage[material]:
					continue
				var arrays: Array = n.mesh.surface_get_arrays(surface)
				var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
				var faces := PackedVector3Array()
				faces.resize(indices.size())
				for i in indices.size():
					faces[i] = vertices[indices[i]]
				var body := StaticBody3D.new()
				body.set_meta("what", "stage surface %d" % surface)
				n.add_child(body)
				var shape := CollisionShape3D.new()
				var trimesh := ConcavePolygonShape3D.new()
				trimesh.backface_collision = true      # many surfaces are single sided and face either way
				trimesh.set_faces(faces)
				shape.shape = trimesh
				body.add_child(shape)
			var box: AABB = n.global_transform * n.get_aabb()
			_bounds = box if _stage_nodes.is_empty() else _bounds.merge(box)
			_stage_nodes.append(n)


func _is_foliage(material: Material) -> bool:
	# a cut-out texture whose opaque pixels are green: the leaves of the trees
	if not material is BaseMaterial3D:
		return false
	var m: BaseMaterial3D = material
	if m.transparency != BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR or m.albedo_texture == null:
		return false
	var image: Image = m.albedo_texture.get_image()
	if image == null:
		return false
	var sum := Vector3.ZERO
	var count := 0
	for y in range(0, image.get_height(), 2):
		for x in range(0, image.get_width(), 2):
			var c: Color = image.get_pixel(x, y)
			if c.a > 0.5:
				sum += Vector3(c.r, c.g, c.b)
				count += 1
	if count < 16:
		return false
	sum /= count
	return sum.y >= sum.x and sum.y > sum.z * 1.25


func _collect_zones(node: Node) -> void:
	var stack: Array = [node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		stack.append_array(n.get_children())
		if n is MeshInstance3D:
			# F1 shows them, as see-through red
			var ghost := StandardMaterial3D.new()
			ghost.albedo_color = Color(1.0, 0.15, 0.1, 0.22)
			ghost.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			ghost.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			ghost.cull_mode = BaseMaterial3D.CULL_DISABLED
			(n as MeshInstance3D).material_override = ghost
			n.visible = Screen.debug
			_zone_nodes.append(n)


func _make_sky(node: MeshInstance3D) -> void:
	# the far scenery (a dome with the sky and a shell behind it) follows the camera and is scaled up so that it
	# lies behind everything the stage has. A flat sheet that is not centred on the dome (stage 2 has one at
	# height -10, 70 times the picture across) is ground: it stays where the stage puts it.
	var sky_mesh := ArrayMesh.new()
	var ground_mesh := ArrayMesh.new()
	var mesh: ArrayMesh = node.mesh
	for i in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(i)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var low := Vector3(INF, INF, INF)
		var high := Vector3(-INF, -INF, -INF)
		for v in vertices:
			low = low.min(v)
			high = high.max(v)
		var flat := high.y - low.y < 0.01 and absf((low.x + high.x) * 0.5) + absf((low.z + high.z) * 0.5) > 100.0
		var target := ground_mesh if flat else sky_mesh
		target.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var material := mesh.surface_get_material(i)
		if material is BaseMaterial3D:
			var copy: BaseMaterial3D = material.duplicate()
			copy.cull_mode = BaseMaterial3D.CULL_BACK if flat else BaseMaterial3D.CULL_DISABLED
			copy.disable_fog = not flat
			material = copy
		target.surface_set_material(target.get_surface_count() - 1, material)
	node.mesh = sky_mesh
	node.custom_aabb = AABB(Vector3.ONE * -1.0e6, Vector3.ONE * 2.0e6)
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.scale = Vector3.ONE * SKY_SCALE
	_sky.append(node)
	if ground_mesh.get_surface_count() > 0:
		var ground := MeshInstance3D.new()
		ground.mesh = ground_mesh
		ground.global_transform = node.get_parent().global_transform if node.get_parent() is Node3D else Transform3D.IDENTITY
		ground.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		node.get_parent().add_child(ground)


func _cast(from: Vector3, to: Vector3) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(from, to)
	return _body.get_world_3d().direct_space_state.intersect_ray(query)


func _argument(prefix: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(prefix):
			return a.substr(prefix.length())
	return ""


func _place(at: Vector3, yaw: float) -> void:
	_body.global_position = at
	_body.velocity = Vector3.ZERO
	_flat = Vector3.ZERO
	_speed = 0.0
	_heading = yaw
	_camera_yaw = yaw
	_start = at
	_started = true
	_update_camera(1.0)


func _ground_below(x: float, y: float, z: float) -> Dictionary:
	# the lowest surface within 40 units under the point: a roof over the place where the skater stands is passed
	var best := {}
	var from := Vector3(x, y + 3.0, z)
	for i in 6:
		var hit := _cast(from, Vector3(x, y - 200.0, z))
		if hit.is_empty():
			break
		var h: float = (hit["position"] as Vector3).y
		if y - h > 40.0 and not best.is_empty():
			break
		best = hit
		from = (hit["position"] as Vector3) + Vector3.DOWN * 0.6
	return best


func _spawn() -> void:
	if not _demo.is_empty():
		var s: Array = _demo["start"]
		var hit := _ground_below(s[0], s[1], s[2])
		var at: Vector3 = (hit["position"] if not hit.is_empty() else Vector3(s[0], s[1], s[2])) + Vector3.UP * 0.5
		_place(at, float(_demo["heading"]) / 65536.0 * TAU)
		return
	var given := _argument("--spawn=")
	if given != "":
		var v := given.split_floats(",")
		var hit := _cast(Vector3(v[0], v[1] + 60.0, v[2]), Vector3(v[0], v[1] - 200.0, v[2]))
		var at: Vector3 = (hit["position"] if not hit.is_empty() else Vector3(v[0], v[1], v[2])) + Vector3.UP * 0.5
		_place(at, float(v[3]) if v.size() > 3 else 0.0)
		return
	var stages: Dictionary = Assets.json("stages")
	var entry: Dictionary = stages.get(str(data.get("stage_id", "1")), {})
	# where most missions of the stage begin, facing what the mission's camera looks at; then the other places
	var places: Array = []
	if entry.has("start"):
		places.append(entry["start"] + entry.get("look", []))
		places.append_array(entry.get("others", []))
	for place in places:
		# a little above the recorded height: the point is where the skater stands, a roof over it must not catch the ray
		var hit := _ground_below(place[0], place[1], place[2])
		if hit.is_empty():
			continue
		var yaw := 0.0
		if place.size() >= 6:
			yaw = atan2(place[3] - place[0], place[5] - place[2])
		_place(hit["position"] + Vector3.UP * 0.5, yaw)
		return
	# no start has ground under it: the nearest floor to the first one, at about its height
	if entry.has("start"):
		var wanted: Array = entry["start"]
		var near := _nearest_floor(Vector3(wanted[0], wanted[1], wanted[2]), 800.0)
		if not near.is_empty():
			var yaw := 0.0
			if entry.has("look"):
				var look: Array = entry["look"]
				yaw = atan2(look[0] - near["position"].x, look[2] - near["position"].z)
			_place(near["position"] + Vector3.UP * 0.5, yaw)
			return
	# nothing there either: level ground near the middle of the stage
	var centre := _bounds.get_center()
	var best := Vector3(centre.x, _bounds.end.y, centre.z)
	var best_score := INF
	var step := maxf(_bounds.size.x, _bounds.size.z) / 40.0
	for gx in range(-20, 21):
		for gz in range(-20, 21):
			var x := centre.x + gx * step
			var z := centre.z + gz * step
			var hit := _cast(Vector3(x, 80.0, z), Vector3(x, -60.0, z))
			if hit.is_empty() or hit["normal"].y < 0.9:
				continue
			# prefer points on the lowest wide floor near the middle
			var score: float = Vector2(x - centre.x, z - centre.z).length() + absf(hit["position"].y) * 6.0
			if score < best_score:
				best_score = score
				best = hit["position"]
	_place(best + Vector3.UP * 0.5, 0.0)


func _load_demo() -> void:
	var index := int(data.get("demo", -1))
	var demos: Array = Assets.json("demos").get("demos", [])
	if index >= 0 and index < demos.size():
		_demo = demos[index]
		_demo_at = 0
		_demo_left = int(_demo["records"][0][0])


func _demo_step(delta: float) -> void:
	# the recorded records are frames of 1/60 s: advance by real time
	_demo_clock += delta * 60.0
	_demo_jump = false
	while _demo_clock >= 1.0 and not _demo.is_empty():
		_demo_clock -= 1.0
		if _demo_left > 0:
			_demo_left -= 1
			continue
		_demo_at += 1
		var records: Array = _demo["records"]
		if _demo_at >= records.size():
			if _background:
				_load_demo()
				_spawn()
			else:
				finished.emit("title", {})
				_demo = {}
			return
		var previous: int = int(records[_demo_at - 1][1])
		var record: Array = records[_demo_at]
		_demo_left = int(record[0])
		if (int(record[1]) & 1) != 0 and (previous & 1) == 0:
			_demo_jump = true


func _stick() -> Vector2:
	if _demo.is_empty():
		return Input.get_vector("left", "right", "up", "down")
	var record: Array = _demo["records"][mini(_demo_at, _demo["records"].size() - 1)]
	var angle := float(record[2]) / 256.0 * TAU
	var strength := float(record[3]) / 255.0
	return Vector2(sin(angle), -cos(angle)) * strength


func _boost_held() -> bool:
	if _demo.is_empty():
		return Input.is_action_pressed("boost")
	var record: Array = _demo["records"][mini(_demo_at, _demo["records"].size() - 1)]
	return (int(record[1]) & 8) != 0


func _jump_pressed() -> bool:
	return Input.is_action_just_pressed("jump") if _demo.is_empty() else _demo_jump


func _load_rails() -> void:
	var entry: Dictionary = Assets.json("stages").get(str(data.get("stage_id", "1")), {})
	for chain in entry.get("rails", []):
		var line := PackedVector3Array()
		for p in chain:
			line.append(Vector3(p[0], p[1], p[2]))
		if line.size() >= 2:
			_rails.append(line)
	if _rails.is_empty():
		return
	# drawn with F1, so that what can be grinded can be seen
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	for line in _rails:
		for i in line.size() - 1:
			mesh.surface_add_vertex(line[i] + Vector3.UP * 0.5)
			mesh.surface_add_vertex(line[i + 1] + Vector3.UP * 0.5)
	mesh.surface_end()
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(1.0, 0.9, 0.0)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.no_depth_test = true
	_rail_view = MeshInstance3D.new()
	_rail_view.mesh = mesh
	_rail_view.material_override = material
	_rail_view.visible = Screen.debug
	add_child(_rail_view)


func _load_cans() -> void:
	var entry: Dictionary = Assets.json("stages").get(str(data.get("stage_id", "1")), {})
	var template := Assets.model("models/items.glb")
	if template == null:
		return
	# the pickups of the stage: [record, node, animation, radius, comes back]. The second table (`items_b`) is drawn as a
	# flat grey can; what it is for is not known, so it is not placed.
	var groups: Array = []
	var soul_places := {}
	for record in entry.get("items_c", []):
		soul_places[Vector3(record[0], record[1], record[2]).snapped(Vector3.ONE * 2.0)] = true
	for record in entry.get("cans", []):
		if soul_places.has(Vector3(record[0], record[1], record[2]).snapped(Vector3.ONE * 2.0)):
			continue
		var small: bool = int(record[3]) == 0
		groups.append([record, "can0" if small else "can1", "spin0" if small else "spin1", 5.0 if small else 7.5, small])
	for record in entry.get("items_c", []):
		groups.append([record, "item_c", "spin4", 5.0, false])
	var scenes := {}
	for g in groups:
		var name: String = g[1]
		if not scenes.has(name):
			var scene: Node3D = template.duplicate()
			for child in scene.get_children():
				if child is MeshInstance3D and child.name != name:
					scene.remove_child(child)
					child.free()
			scenes[name] = scene
		var node: Node3D = scenes[name].duplicate()
		node.position = Vector3(g[0][0], g[0][1], g[0][2])
		add_child(node)
		for child in node.get_children():
			if child is MeshInstance3D:
				child.visibility_range_end = CAN_VIEW
		Assets.play_in(node, g[2])
		_cans.append({"node": node, "pos": node.position, "radius": g[3], "kind": 0 if g[4] else 1, "item": g[1].begins_with("item"), "wait": 0.0, "grow": 1.0})
	for scene in scenes.values():
		scene.free()
	template.free()


func _load_points() -> void:
	# the point lists of the +0x1C table, drawn with F1 (what they are for is not known yet)
	var entry: Dictionary = Assets.json("stages").get(str(data.get("stage_id", "1")), {})
	var chains: Array = entry.get("points", [])
	if chains.is_empty():
		return
	var mesh := ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	for chain in chains:
		for i in chain.size():
			var p := Vector3(chain[i][0], chain[i][1], chain[i][2])
			mesh.surface_add_vertex(p)
			mesh.surface_add_vertex(p + Vector3.UP * 14.0)
			if i > 0:
				mesh.surface_add_vertex(Vector3(chain[i - 1][0], chain[i - 1][1] + 1.0, chain[i - 1][2]))
				mesh.surface_add_vertex(p + Vector3.UP)
	mesh.surface_end()
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.1, 1.0, 1.0)
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.no_depth_test = true
	_points_view = MeshInstance3D.new()
	_points_view.mesh = mesh
	_points_view.material_override = material
	_points_view.custom_aabb = AABB(Vector3.ONE * -1.0e5, Vector3.ONE * 2.0e5)
	_points_view.visible = Screen.debug
	add_child(_points_view)


func _make_car(node: MeshInstance3D) -> void:
	# the vehicles spawned from the sector records of a mission set are parked ones: their task has no update function
	# (`FUN_82379310`); they only react when hit (`FUN_82375e58`, not ported). They are solid here.
	node.create_trimesh_collision()
	_cars.append(node)


# Driving traffic (tools/traffic.py, `FUN_8238D6C8`, `FUN_82378BB8` and its update `FUN_823786F8`): every record of the
# mission script's command 9 is a vehicle that follows a route, a motion with position and angle keys, from its start
# phase, `speed` frames of the route per update, starting again at the end. The update is taken as 1/60 s.
const TRAFFIC_FRAME := 1.0 / 60.0


func _load_traffic() -> void:
	var entry: Dictionary = Assets.json("stages").get(str(data.get("stage_id", "1")), {})
	var info: Dictionary = entry.get("traffic", {})
	var routes: Dictionary = info.get("paths", {})
	for car in info.get("cars", []):
		var route: Dictionary = routes.get(str(int(car["route"])), {})
		var template: MeshInstance3D = _traffic_templates.get(int(car["type"]))
		if route.is_empty() or template == null:
			continue
		var node := MeshInstance3D.new()
		node.mesh = template.mesh
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(node)
		_traffic.append({"node": node, "route": route, "frame": float(route["frames"]) * float(car["phase"]),
				"speed": float(car["speed"])})


func _route_at(route: Dictionary, frame: float) -> Transform3D:
	var pos := _key_vec(route["pos"], frame)
	var ang := _key_vec(route["ang"], frame) * BAMS
	return Transform3D(Basis.from_euler(ang, EULER_ORDER_ZYX), pos)


func _key_vec(keys: Array, frame: float) -> Vector3:
	var last := keys.size() - 1
	if last < 0:
		return Vector3.ZERO
	if frame <= float(keys[0][0]):
		return Vector3(keys[0][1], keys[0][2], keys[0][3])
	if frame >= float(keys[last][0]):
		return Vector3(keys[last][1], keys[last][2], keys[last][3])
	# binary search for the keys around the frame
	var lo := 0
	var hi := last
	while hi - lo > 1:
		var mid := (lo + hi) >> 1
		if float(keys[mid][0]) <= frame:
			lo = mid
		else:
			hi = mid
	var a: Array = keys[lo]
	var b: Array = keys[hi]
	var t := (frame - float(a[0])) / maxf(float(b[0]) - float(a[0]), 1.0)
	return Vector3(lerpf(a[1], b[1], t), lerpf(a[2], b[2], t), lerpf(a[3], b[3], t))


func _update_traffic(delta: float) -> void:
	if _traffic.is_empty():
		return
	_traffic_clock += delta
	var steps := int(_traffic_clock / TRAFFIC_FRAME)
	_traffic_clock -= steps * TRAFFIC_FRAME
	for car in _traffic:
		var route: Dictionary = car["route"]
		var frame: float = float(car["frame"]) + float(car["speed"]) * steps
		if frame > float(route["frames"]) - 1.0:
			frame = 0.0
		car["frame"] = frame
		(car["node"] as MeshInstance3D).global_transform = _route_at(route, frame)


# Spraying. Read from the x86 code (`FUN_004E4440`, the tagging state of the player; `FUN_004E4000`, one gesture of the
# tables in assets/gestures.json): the skater is put on the first standing point of the spot, faces the wall, and has to
# perform the gestures of the step with the stick; a step done moves him to the next point; a failed gesture ends the
# tagging, the spot keeps its state. The stick angle is the game's: 0 up, 65536 a turn, growing towards the left, kept in
# the top byte; the length is a byte over 255. Not ported: the paint strokes drawn while spraying (the picture appears
# when the last step is done), the camera of the tagging, the pictures chosen from the art mask of the spot (random here).
const STICK_DEAD := 0.1
const STICK_FLICK := 0.8


func _load_spots() -> void:
	var entry: Dictionary = Assets.json("stages").get(str(data.get("stage_id", "1")), {})
	var arts: Dictionary = Assets.json("graffiti")
	for sd in entry.get("spots", []):
		var quad: Array = sd.get("quad", [])
		if quad.size() < 6 or sd.get("points", []).is_empty():
			continue
		var holder := Node3D.new()
		add_child(holder)
		# the quad the picture is drawn on: two triangles with their texture coordinates
		var verts := PackedVector3Array()
		var uvs := PackedVector2Array()
		for q in quad:
			verts.append(Vector3(q[0], q[1], q[2]))
			uvs.append(Vector2(q[3], q[4]))
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = verts
		arrays[Mesh.ARRAY_TEX_UV] = uvs
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var decal := MeshInstance3D.new()
		decal.mesh = mesh
		decal.visible = false
		decal.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		holder.add_child(decal)
		# the volume the skater tags from, in the frame of the wall (its front vector turned to +Z)
		var front: Array = sd.get("front", [0.0, 0.0, 1.0])
		var yaw := atan2(float(front[0]), float(front[2]))
		var frame := Basis(Vector3.UP, -yaw)
		var low := Vector3(INF, INF, INF)
		var high := Vector3(-INF, -INF, -INF)
		for v in sd.get("volume", []):
			var w := frame * Vector3(v[0], v[1], v[2])
			low = low.min(w)
			high = high.max(w)
		var first := Vector3(sd["points"][0][0], sd["points"][0][1], sd["points"][0][2])
		var icon := Sprite3D.new()
		icon.texture = Assets.texture("images/sprayy.png")
		icon.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		icon.pixel_size = 0.12
		icon.shaded = false
		icon.position = first + Vector3.UP * 14.0
		holder.add_child(icon)
		var size_key := "256x128" if int(sd["level"]) == 3 else "128x128"
		_spots.append({"data": sd, "node": holder, "decal": decal, "icon": icon, "tagged": false, "next": 0,
				"face": yaw + PI, "frame": frame, "low": low, "high": high, "art": arts.get(size_key, []),
				"first": first})


func _spot_near() -> int:
	var at := _body.global_position
	for i in _spots.size():
		var sp: Dictionary = _spots[i]
		if sp["tagged"]:
			continue
		var local: Vector3 = (sp["frame"] as Basis) * at
		var low: Vector3 = sp["low"]
		var high: Vector3 = sp["high"]
		if local.x >= low.x and local.x <= high.x and local.y >= low.y and local.y <= high.y \
				and local.z >= low.z and local.z <= high.z:
			return i
	return -1


func _update_spots(_delta: float) -> void:
	for i in _spots.size():
		var sp: Dictionary = _spots[i]
		var icon: Sprite3D = sp["icon"]
		icon.visible = not sp["tagged"]
		if not sp["tagged"]:
			icon.position = (sp["first"] as Vector3) + Vector3.UP * (14.0 + sin(Time.get_ticks_msec() * 0.004 + i) * 1.5)
	var near := _spot_near()
	if _tag_hint:
		_tag_hint.visible = near >= 0 and _tag.is_empty() and not _background and _cans_left > 0
	if near >= 0 and _tag.is_empty() and not _grinding and Input.is_action_just_pressed("spray") and not _background:
		_start_tag(near)


func _stick_game() -> Vector2:
	# (angle in the game's 16 bit units from the top byte, length 0..1 in 255 steps)
	var v := Input.get_vector("left", "right", "up", "down")
	if v.length() < 0.01:
		return Vector2(0.0, 0.0)
	var angle := atan2(-v.x, -v.y)
	var byte := int(roundf(angle / TAU * 256.0)) & 0xFF
	if byte > 127:
		byte -= 256
	return Vector2(float(byte * 256), floorf(clampf(v.length(), 0.0, 1.0) * 255.0) / 255.0)


func _angle_diff(a: float, b: float) -> int:
	# FUN_00486870: b - a taken into -32768 .. 32767
	var d := (int(b) & 0xFFFF) - (int(a) & 0xFFFF)
	if d > 0x7FFF:
		d -= 0x10000
	if d < -0x8000:
		d += 0x10000
	return d


func _tag_class() -> int:
	var characters: Array = Assets.json("gestures").get("characters", [])
	var id := int(data.get("character", 0))
	if id >= 0 and id < characters.size():
		return clampi(int(characters[id][2]), 0, 2)
	return 0


func _max_cans() -> int:
	var characters: Array = Assets.json("gestures").get("characters", [])
	var id := int(data.get("character", 0))
	if id >= 0 and id < characters.size():
		return int(characters[id][3])
	return 20


func _start_tag(index: int) -> void:
	var sp: Dictionary = _spots[index]
	if Assets.json("gestures").is_empty():
		return
	# FUN_004E4440 case 0: with no spray can left the spot cannot be started
	if _cans_left < 1:
		return
	var st := _stick_game()
	_tag = {"spot": index, "step": int(sp["next"]), "k": 0, "state": 0, "prev_angle": st.x, "prev_mag": st.y,
			"pause": 0.0, "size": _tag_class()}
	_flat = Vector3.ZERO
	_speed = 0.0
	_body.velocity = Vector3.ZERO
	_place_at_point()


func _place_at_point() -> void:
	# FUN_004E4440 case 0: the skater stands on the point of the step, turned to the wall
	var sp: Dictionary = _spots[_tag["spot"]]
	var pts: Array = sp["data"]["points"]
	var step: int = _tag["step"]
	_body.global_position = Vector3(pts[step][0], pts[step][1], pts[step][2])
	_heading = float(sp["face"])
	_body.rotation.y = _heading
	_tag["state"] = 0
	_tag["k"] = 0
	var start: Array = Assets.json("gestures").get("start", [128])
	_play_loop(int(start[randi() % start.size()]), 1.0)


func _gesture_motion(g: int) -> int:
	# FUN_004E3A30: one of the motions the mask of the gesture allows (the list of the second set is for three
	# entries of the pointer table that are not used here)
	var table: Dictionary = Assets.json("gestures")
	var mask := int((table.get("masks", []) as Array)[g])
	var bits: Array = []
	for b in 32:
		if (mask >> b) & 1:
			bits.append(b)
	if bits.is_empty():
		return MOTION_IDLE
	var list: Array = table["motions_a"]
	return int(list[mini(int(bits[randi() % bits.size()]), list.size() - 1)])


func _gesture() -> int:
	# FUN_004E4000: 0 nothing yet, 1 going on, 2 the step is done, 3 failed
	var table: Dictionary = Assets.json("gestures")
	var seq: Dictionary = table["sequences"][_tag["size"]][_tag["step"]]
	var count: int = seq["count"]
	var gid: int = int(seq["list"][mini(int(_tag["k"]), 2)])
	var g: Array = table["gestures"][gid]
	var a: int = g[0]
	var b: int = g[1]
	var c: int = g[2]
	var e: int = g[4]
	var kind: int = g[6]
	var st := _stick_game()
	var cur: float = st.x
	var mag: float = st.y
	var prev: float = _tag["prev_angle"]
	var prev_mag: float = _tag["prev_mag"]
	var fail := false
	if kind == 1 and _angle_diff(prev, cur) < 0:
		fail = true
	elif kind == 2 and _angle_diff(prev, cur) > 0:
		fail = true
	if mag <= STICK_DEAD:
		fail = true
	if int(_tag["state"]) == 0:
		if kind == 0:
			if mag <= STICK_FLICK or prev_mag > STICK_FLICK:
				return 1
			if _angle_diff(a, cur) <= 0 or _angle_diff(b, cur) >= 0:
				return 1
			_play_loop(_gesture_motion(gid), 1.0)
			_tag["k"] = int(_tag["k"]) + 1
			if int(_tag["k"]) < count:
				return 1
			return 2
		if _angle_diff(a, prev) <= 0 or _angle_diff(b, prev) >= 0 or mag <= STICK_DEAD:
			return 0
		if kind == 1:
			if _angle_diff(c, prev) > 0 or _angle_diff(c, cur) < 0:
				return 0
		else:
			if _angle_diff(c, prev) < 0 or _angle_diff(c, cur) > 0:
				return 0
		_play_loop(_gesture_motion(gid), 1.0)
		_tag["state"] = 1
	elif int(_tag["state"]) != 1:
		return 1
	if fail:
		return 3
	if kind == 1:
		if _angle_diff(e, prev) <= 0 and _angle_diff(e, cur) >= 0:
			_tag["k"] = int(_tag["k"]) + 1
			_tag["state"] = 0
			if count <= int(_tag["k"]):
				return 2
	elif kind == 2:
		if _angle_diff(e, prev) >= 0 and _angle_diff(e, cur) <= 0:
			_tag["k"] = int(_tag["k"]) + 1
			_tag["state"] = 0
			if count <= int(_tag["k"]):
				return 2
	return 1


func _update_tag(delta: float) -> void:
	var sp: Dictionary = _spots[_tag["spot"]]
	_body.velocity = Vector3.ZERO
	_flat = Vector3.ZERO
	_speed = 0.0
	if float(_tag["pause"]) > 0.0:
		# after a failed gesture the skater stands a moment (FUN_004E3BE0 plays pose 0x85 / 0x84)
		_tag["pause"] = float(_tag["pause"]) - delta
		if float(_tag["pause"]) <= 0.0:
			_tag = {}
		_update_camera(delta)
		return
	if Input.is_action_just_pressed("jump"):
		_tag = {}
		return
	var result := _gesture()
	if result == 2 or result == 3:
		_cans_left = maxi(_cans_left - 1, 0)       # FUN_004E3C40 and FUN_004E3BE0 take one can
	if result == 2:
		# FUN_004E3C40: the next point; after the last one the spot is done
		sp["next"] = int(_tag["step"]) + 1
		if int(sp["next"]) >= (sp["data"]["points"] as Array).size():
			_finish_tag(sp)
			_tag = {}
			_update_camera(delta)
			return
		_tag["step"] = int(sp["next"])
		_place_at_point()
	elif result == 3:
		_tag["pause"] = 0.5
		_play_loop(133, 1.0)
	if not _tag.is_empty():
		var st := _stick_game()
		_tag["prev_angle"] = st.x
		_tag["prev_mag"] = st.y
	_update_camera(delta)


func _finish_tag(sp: Dictionary) -> void:
	sp["tagged"] = true
	var arts: Array = sp["art"]
	if not arts.is_empty():
		var texture := Assets.texture(str(arts[randi() % arts.size()]))
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.albedo_texture = texture
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
		material.alpha_scissor_threshold = 0.3
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		(sp["decal"] as MeshInstance3D).material_override = material
		(sp["decal"] as MeshInstance3D).visible = true


# What the game does with the objects it spawns from the dynamic object table of a stage (read from the code of the
# task classes `FUN_82382b10`, `FUN_8237b270` and the motion of the table):
#  - a pole (type 2): when hit it turns to face `atan2(camera z, -camera x)` and plays a motion of 17 frames, one a
#    frame, that swings its shaft (second object) about its own X axis: keys every 2 frames of 0, -4484, 4004, -2730,
#    2184, -1456, 910, -364, 0 (65536 per turn);
#  - a cone (type 27, class `FUN_8237b270`): the first hit gives it the speed of the hitter (x and z) and half of it
#    upwards, a spin about all three axes of up to 600, 800 and 1000 per frame, gravity 0.098 a frame, and it is gone
#    after 60 frames.
# The frame is taken as 1/60 s.
const POLE_KEYS := [0, -4484, 4004, -2730, 2184, -1456, 910, -364, 0]
const POLE_FRAMES := 17
const BAMS := TAU / 65536.0
const PROP_FRAME := 1.0 / 60.0
const CONE_GRAVITY := 0.098
const CONE_LIFE := 60


func _update_props(delta: float) -> void:
	var at := _body.global_position
	var cam := _camera.global_position
	for p in _props:
		var node: Node3D = p["node"]
		var rest: Transform3D = p["rest"]
		var state: int = p["state"]
		if state == 0:
			var local := rest.affine_inverse() * at
			var half := 2.5 + BODY_RADIUS
			if absf(local.x) < half and absf(local.z) < half and local.y > -4.0 and local.y < 14.0:
				p["state"] = 1
				p["frame"] = 0.0
				p["clock"] = 0.0
				if _trace:
					print("prop hit ", node.name)
				if p["cone"]:
					var frame_velocity := _flat / 60.0
					p["v"] = Vector3(frame_velocity.x, frame_velocity.length() * 0.5, frame_velocity.z)
					p["spin"] = Vector3(randf() * 600.0, randf() * 800.0, randf() * 1000.0) * BAMS
					p["euler"] = rest.basis.get_euler(EULER_ORDER_ZYX)
				else:
					# the swing is turned to the direction of atan2(camera z, -camera x) in the game's own angles
					var yaw := atan2(cam.z, -cam.x)
					p["yaw_basis"] = Basis(Vector3.UP, yaw)
			continue
		p["clock"] = float(p["clock"]) + delta
		var steps := int(float(p["clock"]) / PROP_FRAME)
		if steps <= 0:
			continue
		p["clock"] = float(p["clock"]) - steps * PROP_FRAME
		if p["cone"]:
			var pos := node.global_position
			var v: Vector3 = p["v"]
			var euler: Vector3 = p["euler"]
			var spin: Vector3 = p["spin"]
			for i in steps:
				pos += v
				v.y -= CONE_GRAVITY
				euler += spin
				p["frame"] = float(p["frame"]) + 1.0
			p["v"] = v
			p["euler"] = euler
			node.global_transform = Transform3D(Basis.from_euler(euler, EULER_ORDER_ZYX), pos)
			if float(p["frame"]) > CONE_LIFE:
				node.visible = false
				p["state"] = 2
		else:
			p["frame"] = float(p["frame"]) + steps
			var f: float = p["frame"]
			if f >= POLE_FRAMES - 1:
				p["state"] = 0
				f = 0.0
			var k := int(f / 2.0)
			var a: float = float(POLE_KEYS[mini(k, 8)])
			var b: float = float(POLE_KEYS[mini(k + 1, 8)])
			var angle := lerpf(a, b, (f - k * 2.0) / 2.0) * BAMS
			var tilt: Node3D = p["tilt"]
			if tilt:
				# the shaft turns about the X axis of the pole, which has been turned to the direction above
				node.global_transform = Transform3D((p["yaw_basis"] as Basis), rest.origin)
				tilt.transform = Transform3D(Basis(Vector3.RIGHT, angle), Vector3.ZERO)
			if p["state"] == 0:
				node.global_transform = rest
				if tilt:
					tilt.transform = Transform3D.IDENTITY


func _update_cans(delta: float) -> void:
	# a can is taken by touching it; a small one grows back in a minute, a large one does not come back
	var at := _body.global_position + Vector3.UP * BODY_TALL * 0.5
	for can in _cans:
		var node: Node3D = can["node"]
		var wait: float = can["wait"]
		if wait < 0.0:
			continue
		if wait > 0.0:
			wait = maxf(wait - delta, 0.0)
			can["wait"] = wait
			if wait == 0.0:
				node.visible = true
				can["grow"] = 0.1
				node.scale = Vector3.ONE * 0.1
			continue
		var grow: float = can["grow"]
		if grow < 1.0:
			grow = minf(grow + delta * 6.0, 1.0)
			can["grow"] = grow
			node.scale = Vector3.ONE * grow
		if at.distance_to(can["pos"]) < float(can["radius"]) + BODY_RADIUS:
			if can["item"]:
				_item_count += 1
			else:
				_can_count += 1
				# the pickup types 0x14 and 0x15 of the player code add 1 and 5 cans; taken to be the small and
				# the large can in that order
				_cans_left = mini(_cans_left + (1 if can["kind"] == 0 else 5), _max_cans())
			_can_label.text = "CANS %d   ITEMS %d" % [_can_count, _item_count]
			_can_label.visible = Screen.debug
			node.visible = false
			can["wait"] = CAN_RESPAWN if can["kind"] == 0 else -1.0


func _nearest_rail(at: Vector3) -> Dictionary:
	# the closest point of any rail: {rail, seg, t, distance, point}
	var best := {}
	var best_distance := INF
	for r in _rails.size():
		var line: PackedVector3Array = _rails[r]
		for i in line.size() - 1:
			var a := line[i]
			var b := line[i + 1]
			var ab := b - a
			var len2 := ab.length_squared()
			var t := 0.0 if len2 < 0.0001 else clampf((at - a).dot(ab) / len2, 0.0, 1.0)
			var point := a + ab * t
			var distance := point.distance_to(at)
			if distance < best_distance:
				best_distance = distance
				best = {"rail": r, "seg": i, "t": t, "distance": distance, "point": point}
	return best


func _start_grind(hit: Dictionary) -> void:
	_grinding = true
	_g_rail = hit["rail"]
	_g_seg = hit["seg"]
	_g_t = hit["t"]
	var line: PackedVector3Array = _rails[_g_rail]
	var along := line[_g_seg + 1] - line[_g_seg]
	along.y = 0.0
	var heading := Vector3(sin(_heading), 0.0, cos(_heading))
	_g_dir = 1 if along.dot(heading) >= 0.0 else -1
	_speed = maxf(_speed, GRIND_SPEED)
	_fallen = 0.0
	_oneshot = 0.0
	_play_loop(MOTION_GRIND, 1.0)


func _grind(delta: float) -> void:
	if _trace and Engine.get_physics_frames() % 15 == 0:
		print("trace grind rail ", _g_rail, " seg ", _g_seg, " t ", snappedf(_g_t, 0.01), " at ", _body.global_position, " speed ", snappedf(_speed, 0.1))
	var line: PackedVector3Array = _rails[_g_rail]
	var remaining := _speed * delta
	var finished := false
	while remaining > 0.0:
		var a := line[_g_seg]
		var b := line[_g_seg + 1]
		var length := a.distance_to(b)
		if length < 0.001:
			length = 0.001
		var here := _g_t * length
		var available := (length - here) if _g_dir > 0 else here
		if remaining < available:
			_g_t += _g_dir * remaining / length
			remaining = 0.0
		else:
			remaining -= available
			var next := _g_seg + _g_dir
			if next < 0 or next >= line.size() - 1:
				_g_t = 1.0 if _g_dir > 0 else 0.0
				finished = true
				break
			_g_seg = next
			_g_t = 0.0 if _g_dir > 0 else 1.0
	var from := line[_g_seg]
	var to := line[_g_seg + 1]
	var along := (to - from).normalized() * float(_g_dir)
	_body.global_position = from.lerp(to, _g_t) + Vector3.UP * 0.2
	_heading = atan2(along.x, along.z)
	_body.rotation.y = _heading
	_body.velocity = Vector3.ZERO
	_flat = Vector3(along.x, 0.0, along.z) * _speed
	_speed = move_toward(_speed, GRIND_SPEED * 0.8, 6.0 * delta)
	if Input.is_action_just_pressed("jump") or finished:
		# off the rail: a hop, or the end of it launches the skater the way it points
		var velocity := along * _speed
		velocity.y = JUMP_SPEED * (0.9 if not finished else 0.55) + maxf(along.y * _speed, 0.0)
		_body.velocity = velocity
		_flat = Vector3(velocity.x, 0.0, velocity.z)
		_grinding = false
		_g_cool = 0.4
		_air_time = 0.0
		_sfx(_se_jump)
	if _model:
		_model.rotation.z = lerpf(_model.rotation.z, 0.0, clampf(delta * 8.0, 0.0, 1.0))
	_play_loop(MOTION_GRIND, 1.0)
	_update_camera(delta)


func _nearest_floor(at: Vector3, radius: float) -> Dictionary:
	# the closest flat surface below `at` (looking down to 450 units under it), searched in rings round it
	var best := {}
	var best_distance := INF
	var ring := 0.0
	while ring <= radius and best.is_empty():
		var count := maxi(1, int(ring / 25.0) * 2)
		for k in count:
			var angle := TAU * float(k) / float(count)
			var x := at.x + cos(angle) * ring
			var z := at.z + sin(angle) * ring
			var hit := _cast(Vector3(x, at.y + 80.0, z), Vector3(x, at.y - 450.0, z))
			if hit.is_empty() or hit["normal"].y < 0.9:
				continue
			var distance := ring + absf(hit["position"].y - at.y) * 0.1
			if distance < best_distance:
				best_distance = distance
				best = hit
		ring += 25.0
	return best


func _physics_process(delta: float) -> void:
	if not _started:
		return
	_g_cool = maxf(_g_cool - delta, 0.0)
	if not _demo.is_empty():
		_demo_step(delta)
	_clock_left = maxf(_clock_left - delta, 0.0)
	_hud_view.time_left = _clock_left
	_hud_view.cans = _cans_left
	_update_cans(delta)
	_update_props(delta)
	_update_spots(delta)
	_update_traffic(delta)
	if not _tag.is_empty():
		_update_tag(delta)
		return
	if _grinding:
		_grind(delta)
		return
	var grounded := _body.is_on_floor()
	if _trace and Engine.get_physics_frames() % 30 == 0:
		print("trace state grounded ", grounded, " speed ", snappedf(_speed, 0.1), " motion ", _current_motion, " fallen ", snappedf(_fallen, 0.01), " air ", snappedf(_air_time, 0.01), " y ", snappedf(_body.global_position.y, 0.1))
	_fallen = maxf(_fallen - delta, 0.0)
	_oneshot = maxf(_oneshot - delta, 0.0)
	_since_change += delta
	_coyote = COYOTE_TIME if grounded else maxf(_coyote - delta, 0.0)
	_jump_buffer = maxf(_jump_buffer - delta, 0.0)
	if _jump_pressed():
		_jump_buffer = JUMP_BUFFER
	var was_air_time := _air_time
	_air_time = 0.0 if grounded else _air_time + delta

	var down := _fallen > 0.0
	if not down and _g_cool <= 0.0 and not _rails.is_empty() and (not grounded or Input.is_action_just_pressed("jump")):
		# in the air next to a rail, or jumping at one: the skater lands on it and grinds
		var hit := _nearest_rail(_body.global_position + Vector3.UP * 2.0)
		var near := false
		if not hit.is_empty():
			var offset: Vector3 = _body.global_position - hit["point"]
			# the feet within reach of the rail: close sideways, from a little below to well above it
			near = Vector2(offset.x, offset.z).length() < GRIND_RADIUS and offset.y > -4.0 and offset.y < 9.0
		if near and _body.velocity.y < 30.0:
			_start_grind(hit)
			_grind(delta)
			return
	var input := Vector2.ZERO if down else _stick()
	var boosting := not down and _boost_held()
	var forward := Vector3(sin(_camera_yaw), 0.0, cos(_camera_yaw))
	var rightward := Vector3(-cos(_camera_yaw), 0.0, sin(_camera_yaw))
	# up on the stick moves away from the camera
	var wish := rightward * input.x - forward * input.y
	var steering := wish.length() > 0.1
	var braking := false
	var before := _heading
	if down:
		_speed = move_toward(_speed, 0.0, BRAKE * delta)
	elif steering:
		var target := atan2(wish.x, wish.z)
		if absf(angle_difference(_heading, target)) > 2.2 and _speed > 10.0 and grounded:
			# pulling against the direction of travel brakes before the turn
			_speed = move_toward(_speed, 0.0, BRAKE * delta)
			braking = true
		else:
			# the game turns (0.2 + 0.8 * (1 - speed / 4.63)) * 10 degrees a frame (the ground handler)
			var turn := (0.2 + 0.8 * (1.0 - clampf(_speed / (4.63 * 60.0), 0.0, 1.0))) * TURN_RATE
			_heading = rotate_toward(_heading, target, turn * delta)
			var limit := (BOOST_SPEED if boosting else MAX_SPEED) * minf(wish.length(), 1.0)
			var rate := BOOST_ACCELERATION if boosting and limit > _speed else ACCELERATION
			_speed = lerpf(_speed, limit, 1.0 - exp(-(rate if grounded else rate * 0.3) * delta))
	else:
		_speed = lerpf(_speed, 0.0, 1.0 - exp(-(COAST if grounded else 0.3) * delta))
		if _speed < 8.3:
			_speed = 0.0

	if grounded and not down:
		# hills: speed is gained downhill and lost uphill, along the way the skater is heading
		var floor_normal := _body.get_floor_normal()
		var downhill := Vector3.DOWN - floor_normal * Vector3.DOWN.dot(floor_normal)
		_speed = maxf(_speed + downhill.dot(Vector3(sin(_heading), 0.0, cos(_heading))) * SLOPE_PULL * delta, 0.0)
	var run := Vector3(sin(_heading), 0.0, cos(_heading)) * _speed
	_flat = _flat.lerp(run, 1.0 - exp(-(GRIP if grounded else AIR_GRIP) * delta))
	var velocity := _body.velocity
	velocity.x = _flat.x
	velocity.z = _flat.z
	if grounded:
		velocity.y = maxf(velocity.y, -1.0)
	else:
		if _was_grounded and _floor_vy > 2.0:
			# left the ground going up (the end of a ramp): keep going up
			velocity.y = maxf(velocity.y, _floor_vy)
		velocity.y -= GRAVITY * delta
	if _jump_buffer > 0.0 and _coyote > 0.0 and not down:
		velocity.y = JUMP_SPEED + maxf(_floor_vy, 0.0)
		_sfx(_se_jump)
		_jump_buffer = 0.0
		_coyote = 0.0
		_oneshot = 0.0
	_body.velocity = velocity
	_step_up(_flat * delta)
	var into := Vector3(_flat.x, 0.0, _flat.z)
	_body.move_and_slide()
	_was_grounded = grounded
	if _body.is_on_floor():
		_floor_vy = _body.get_real_velocity().y
	# running into something takes the speed with it, and a hard hit knocks the skater down
	var worst := 0.0
	for i in _body.get_slide_collision_count():
		var hit := _body.get_slide_collision(i)
		if hit.get_normal().y < 0.4:
			worst = maxf(worst, -hit.get_normal().dot(into))
			var thing: Node = hit.get_collider() as Node
			_blocker = "%s at %s" % [thing.get_meta("what", "?") if thing else "?", str(hit.get_position().snapped(Vector3.ONE * 0.1))]
	var real := Vector2(_body.get_real_velocity().x, _body.get_real_velocity().z)
	if _speed > 1.0 and real.length() < _speed * 0.5:
		_speed = real.length()
		_flat = Vector3(real.x, 0.0, real.y)
	if worst > KNOCK_DOWN_SPEED and not down:
		_knock_down(worst)
	elif _body.is_on_floor() and not grounded and maxf(was_air_time, _air_time) > 0.3 and _fallen <= 0.0:
		if was_air_time > 1.0:
			_sfx(_se_land)
		_play_once(_landing_motion(), 1.0)

	_keep_inside()
	if _body.global_position.y < _bounds.position.y - 200.0:
		_body.global_position = _start
		_body.velocity = Vector3.ZERO
		_flat = Vector3.ZERO
		_speed = 0.0
	_body.rotation.y = _heading
	# lean into the turn
	var turn_rate := angle_difference(before, _heading) / maxf(delta, 0.0001)
	var lean_goal := clampf(-turn_rate * 0.09, -0.45, 0.45) * clampf(_speed / MAX_SPEED, 0.0, 1.0)
	_lean = lerpf(_lean, lean_goal, clampf(delta * 8.0, 0.0, 1.0))
	if _model:
		_model.rotation.z = _lean
	_animate(delta, _body.is_on_floor(), steering, braking, boosting)
	_update_camera(delta)
	if _trace and Engine.get_physics_frames() % 30 == 0:
		print("trace ", _body.global_position, " speed ", snappedf(_speed, 0.1), " floor ", _body.is_on_floor(),
				" heading ", snappedf(rad_to_deg(_heading), 1.0), " motion ", _current_motion,
				" fallen ", snappedf(_fallen, 0.1), " grind ", _grinding, " blocked by ", _blocker)
	if _hud.visible:
		_hud.text = "%s   speed %.0f   motion %d   cans %d   at %s\n blocked by: %s\n sound test (, . /): %s\n arrows/WASD move   Shift boost   Space jump   Q E R F camera   Esc back   [ ] step through motions" % [
				str(data.get("name", "")), _speed, _current_motion, _can_count, str(_body.global_position.snapped(Vector3.ONE)), _blocker,
				_effect_labels[_effect_index] if _effect_index >= 0 else "-"]


func _landing_motion() -> int:
	# FUN_004ED700: by the speed on landing, with the thresholds 0.92593 and 1.85185 a frame of the shared block
	if _speed <= 0.5:
		return 16
	if _speed < 0.92593 * 60.0:
		return 13
	if _speed < 1.85185 * 60.0:
		return 12
	return 14


func _knock_down(impact: float) -> void:
	var motion := MOTION_FALL_HARD if impact > KNOCK_DOWN_SPEED * 1.5 else MOTION_FALL_LIGHT
	_fallen = _length_of(motion)
	_speed = 0.0
	_flat = Vector3.ZERO
	_sfx(_se_fall)
	_play_once(motion, 1.0)


func _length_of(motion: int) -> float:
	if _player and _player.has_animation("m%03d" % motion):
		return _player.get_animation("m%03d" % motion).length
	return 1.0


func _play_once(motion: int, speed: float) -> void:
	# a motion that plays through, and holds the choice of the next one until it is done
	if _player == null:
		return
	var name := "m%03d" % motion
	if not _player.has_animation(name):
		return
	_player.get_animation(name).loop_mode = Animation.LOOP_NONE
	_player.speed_scale = speed
	_player.play(name, 0.1)
	_current_motion = motion
	_oneshot = _length_of(motion) / speed
	_since_change = 0.0


func _play_loop(motion: int, speed: float) -> void:
	if _player == null:
		return
	if motion == _current_motion and _player.is_playing():
		_player.speed_scale = speed
		return
	var name := "m%03d" % motion
	if not _player.has_animation(name):
		return
	_player.get_animation(name).loop_mode = Animation.LOOP_LINEAR
	_player.speed_scale = speed
	_player.play(name, 0.15)
	_current_motion = motion
	_since_change = 0.0


func _play_hold(motion: int) -> void:
	# plays through once and stays on the last frame
	if _player == null or motion == _current_motion:
		return
	var name := "m%03d" % motion
	if not _player.has_animation(name):
		return
	_player.get_animation(name).loop_mode = Animation.LOOP_NONE
	_player.speed_scale = 1.0
	_player.play(name, 0.12)
	_current_motion = motion
	_since_change = 0.0


func _animate(delta: float, grounded: bool, steering: bool, braking: bool, boosting: bool) -> void:
	if _player == null:
		return
	if _debug_motion >= 0:
		_play_loop(_debug_motion, 1.0)
		return
	if _fallen > 0.0:
		return
	var moving := _speed > 4.0
	if not grounded and _air_time > 0.05:
		# the player code sets motion 96 for the take-off and 97 for the air (both with the same state flag)
		_play_hold(MOTION_JUMP if _air_time < 0.35 else MOTION_AIR)
		_idle_time = 0.0
		return
	if _oneshot > 0.0 and not steering and not moving:
		return
	if braking:
		_play_loop(MOTION_BRAKE, 1.0)
		return
	if not moving and not steering:
		_idle_time += delta
		if _idle_time > 6.0:
			_play_loop(MOTION_BORED[1], 1.0)
		elif _idle_time > 3.0:
			_play_loop(MOTION_BORED[0], 1.0)
		else:
			_play_loop(MOTION_IDLE, 1.0)
		return
	_idle_time = 0.0
	if _oneshot > 0.0 and not steering:
		return
	if boosting:
		_play_loop(MOTION_BOOST, 1.0)
	elif steering:
		_play_loop(MOTION_SKATE, 1.0)
	else:
		_play_loop(MOTION_COAST, 1.0)


func _is_gesture(_motion: int) -> bool:
	return false


func _step_up(move: Vector3) -> void:
	# small ledges (kerbs, steps) are climbed instead of stopping the skater
	if not _body.is_on_floor() or move.length() < 0.01:
		return
	var here := _body.global_transform
	if not _body.test_move(here, move):
		return
	var raised := here.translated(Vector3.UP * STEP)
	if _body.test_move(here, Vector3.UP * STEP):
		return
	if not _body.test_move(raised, move):
		_body.global_position += Vector3.UP * STEP


func _keep_inside() -> void:
	# a last resort: stay within the extent of the stage's geometry
	var lo := _bounds.position - Vector3(BOUNDS_MARGIN, 0.0, BOUNDS_MARGIN)
	var hi := _bounds.end + Vector3(BOUNDS_MARGIN, 0.0, BOUNDS_MARGIN)
	var p := _body.global_position
	var clamped := Vector3(clampf(p.x, lo.x, hi.x), p.y, clampf(p.z, lo.z, hi.z))
	if clamped != p:
		_body.global_position = clamped
		_speed *= 0.5


func _update_camera(delta: float) -> void:
	var look := Input.get_vector("look_left", "look_right", "look_down", "look_up")
	if absf(look.x) > 0.01:
		_camera_yaw -= look.x * 2.2 * delta
	elif delta < 1.0:
		# swing round behind the skater, quicker the faster the skater goes
		var follow := clampf(_speed / MAX_SPEED, 0.0, 1.0) * CAMERA_FOLLOW
		_camera_yaw += angle_difference(_camera_yaw, _heading) * (1.0 - exp(-follow * delta))
	_camera_pitch = clampf(_camera_pitch + look.y * 1.4 * delta, 0.05, 1.2)
	var focus := _body.global_position + Vector3.UP * BODY_HEIGHT
	var back := Vector3(-sin(_camera_yaw) * cos(_camera_pitch), sin(_camera_pitch),
			-cos(_camera_yaw) * cos(_camera_pitch))
	var distance := CAMERA_DISTANCE + clampf(_speed / MAX_SPEED, 0.0, 1.5) * 10.0
	var wanted := focus + back * distance
	# keep the camera out of walls
	var hit := _cast(focus, wanted)
	if not hit.is_empty():
		wanted = hit["position"] + hit["normal"] * 1.0
	_camera.position = _camera.position.lerp(wanted, clampf(delta * 8.0, 0.0, 1.0)) if delta < 1.0 else wanted
	_camera.look_at(focus + Vector3.UP * (CAMERA_HEIGHT - BODY_HEIGHT) * 0.2)
	var fov := 70.0 + clampf(_speed / BOOST_SPEED, 0.0, 1.0) * 12.0
	_camera.fov = lerpf(_camera.fov, fov, clampf(delta * 3.0, 0.0, 1.0)) if delta < 1.0 else fov
	for sky in _sky:
		sky.global_position = _camera.global_position


func debug_changed() -> void:
	if _hud:
		_hud.visible = Screen.debug
	for n in _zone_nodes:
		n.visible = Screen.debug
	if _rail_view:
		_rail_view.visible = Screen.debug
	if _points_view:
		_points_view.visible = Screen.debug
	if not Screen.debug:
		_debug_motion = -1


func _unhandled_input(event: InputEvent) -> void:
	if not _demo.is_empty() and (event.is_action_pressed("back") or event.is_action_pressed("confirm")
			or (event is InputEventKey and event.pressed and not event.echo and event.keycode != KEY_F1)):
		_demo = {}
		finished.emit("title", {})
	elif event.is_action_pressed("back"):
		finished.emit("garage", {"character": data.get("character", 0)})
	elif event is InputEventKey and event.pressed and not event.echo and Screen.debug:
		if event.keycode == KEY_BRACKETRIGHT:
			_debug_motion = maxi(_debug_motion, -1) + 1
		elif event.keycode == KEY_BRACKETLEFT:
			_debug_motion = maxi(_debug_motion - 1, -1)
		elif (event.keycode == KEY_PERIOD or event.keycode == KEY_COMMA) and not _effects.is_empty():
			var step := 1 if event.keycode == KEY_PERIOD else -1
			_effect_index = (_effect_index + step + _effects.size()) % _effects.size()
			_sfx(_effects[_effect_index])
		elif event.keycode == KEY_SLASH and _effect_index >= 0:
			_sfx(_effects[_effect_index])
	elif event is InputEventMouseMotion and event.button_mask & MOUSE_BUTTON_MASK_RIGHT:
		_camera_yaw -= event.relative.x * 0.005
		_camera_pitch = clampf(_camera_pitch + event.relative.y * 0.004, 0.05, 1.2)
