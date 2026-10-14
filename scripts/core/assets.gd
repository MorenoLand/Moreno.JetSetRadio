class_name Assets
extends RefCounted
# Reads the files written by the tools (see docs/tools.md): models, sprite sheets and the description of the screens.

const ROOT := "res://assets/"
const OVERRIDE := "JETSET_ASSETS"      # environment variable: use the exported files from another folder

static var _json: Dictionary = {}
static var _textures: Dictionary = {}


static func available() -> bool:
	return FileAccess.file_exists(path("screens.json")) and FileAccess.file_exists(path("skaters.json"))


static func path(relative: String) -> String:
	var other := OS.get_environment(OVERRIDE)
	if other != "":
		return other.trim_suffix("/") + "/" + relative
	return ProjectSettings.globalize_path(ROOT + relative)


static func json(name: String) -> Variant:
	if not _json.has(name):
		var file := path(name + ".json")
		_json[name] = JSON.parse_string(FileAccess.get_file_as_string(file)) if FileAccess.file_exists(file) else {}
	return _json[name]


static func screen(name: String) -> Dictionary:
	var all: Dictionary = json("screens")
	return all.get(name, {})


static func model(relative: String) -> Node3D:
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	if doc.append_from_file(path(relative), state) != OK:
		push_warning("could not read " + relative)
		return null
	return doc.generate_scene(state)


static func texture(relative: String) -> Texture2D:
	if not _textures.has(relative):
		var image := Image.load_from_file(path(relative))
		_textures[relative] = ImageTexture.create_from_image(image) if image else null
	return _textures[relative]


static func player_of(node: Node) -> AnimationPlayer:
	if node is AnimationPlayer:
		return node
	for child in node.get_children():
		var found := player_of(child)
		if found:
			return found
	return null


static func play_in(root: Node, animation: String, loop: bool = true, speed: float = 1.0) -> AnimationPlayer:
	# Every animation of an imported file lives in one player, which plays one at a time; trees that animate
	# together each get a player of their own, all working on the same nodes.
	var library := player_of(root)
	if library == null or not library.has_animation(animation):
		return null
	var player := AnimationPlayer.new()
	root.add_child(player)
	player.root_node = player.get_path_to(root)
	var clip: Animation = library.get_animation(animation)
	clip.loop_mode = Animation.LOOP_LINEAR if loop else Animation.LOOP_NONE
	var set := AnimationLibrary.new()
	set.add_animation("a", clip)
	player.add_animation_library("", set)
	player.speed_scale = speed
	player.play("a")
	return player


static func vertical_fov(horizontal_radians: float) -> float:
	# the games pictures are 4:3 and the angle they store is the horizontal one; this is the vertical angle of a
	# 4:3 view, which stays right when the window is wider
	return rad_to_deg(2.0 * atan(tan(horizontal_radians * 0.5) * 0.75))
