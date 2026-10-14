class_name Screen
extends Node
# A full-window screen of the game flow. The 2D parts are laid out in the 640 x 480 picture of the original and
# scaled to fit; 3D parts are children of the screen.

signal finished(next: String, data: Dictionary)

const PICTURE := Vector2(640, 480)

# F1 switches the debugging aids on or off: the text strip in a stage and the choice of the area after the garage
static var debug := false

var data: Dictionary = {}     # what the previous screen passed on
var layer: CanvasLayer
var root_control: Control
var canvas: Control


func _init() -> void:
	layer = CanvasLayer.new()
	add_child(layer)
	root_control = Control.new()
	root_control.set_anchors_preset(Control.PRESET_FULL_RECT)
	root_control.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root_control.resized.connect(_fit)
	layer.add_child(root_control)
	canvas = Control.new()
	canvas.size = PICTURE
	canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root_control.add_child(canvas)


func debug_changed() -> void:
	pass


func light_scene(environment: Environment, camera: Camera3D) -> void:
	# the lighting the garage sets up: a white light that travels forward and down from the camera
	# (0, -0.4, 0.34 in view space) and a bluish ambient colour (95, 117, 151)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(95.0 / 255.0, 117.0 / 255.0, 151.0 / 255.0)
	environment.ambient_light_energy = 1.0
	var sun := DirectionalLight3D.new()
	sun.light_energy = 0.9
	sun.shadow_enabled = false
	camera.add_child(sun)
	sun.basis = Basis.looking_at(Vector3(0.0, -0.4, -0.34).normalized(), Vector3.UP)


func _fit() -> void:
	var s := minf(root_control.size.x / PICTURE.x, root_control.size.y / PICTURE.y)
	canvas.scale = Vector2(s, s)
	canvas.position = (root_control.size - PICTURE * s) * 0.5


func sprite(info: Dictionary, parent: Control = null) -> TextureRect:
	# a sprite of screens.json: a rectangle of a sheet drawn at its place in the 640 x 480 picture
	var rect := TextureRect.new()
	var sheet := Assets.texture(str(info.get("sheet", "")))
	if sheet == null:
		return rect
	var uv: Array = info["uv"]
	var atlas := AtlasTexture.new()
	atlas.atlas = sheet
	var w := sheet.get_width()
	var h := sheet.get_height()
	atlas.region = Rect2(uv[0] * w, uv[1] * h, (uv[2] - uv[0]) * w, (uv[3] - uv[1]) * h)
	rect.texture = atlas
	rect.stretch_mode = TextureRect.STRETCH_SCALE
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.position = Vector2(info["x"], info["y"])
	rect.size = Vector2(info["w"], info["h"])
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var color: int = int(info["colors"][0])
	rect.modulate = Color(((color >> 16) & 0xFF) / 255.0, ((color >> 8) & 0xFF) / 255.0, (color & 0xFF) / 255.0,
			((color >> 24) & 0xFF) / 255.0)
	(parent if parent else canvas).add_child(rect)
	return rect
