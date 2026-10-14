class_name CornerLoading
extends Control
# The head with the speech bubble of the PC release, small in the bottom right corner of a screen while data is being
# read behind it (the title reads the stage of its demonstration, for example).

static var active := false


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)


func _process(_delta: float) -> void:
	queue_redraw()


func _draw() -> void:
	if not active:
		return
	var picture := Assets.texture("images/loading_EN.png")
	if picture == null:
		return
	var u := size.y / 1125.0
	var w := 340.0 * u * 1.0
	var h := w * picture.get_height() / picture.get_width()
	draw_texture_rect(picture, Rect2(Vector2(size.x - w - 24.0 * u, size.y - h - 20.0 * u), Vector2(w, h)), false)
