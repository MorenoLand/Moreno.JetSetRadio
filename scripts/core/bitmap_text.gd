class_name BitmapText
extends Control
# Text in one of the game's bitmap fonts (assets/fonts/NAME.png and NAME.json, written by tools/fnt.py). The letters
# are white with a dark edge, so `tint` colours the letters and leaves the edge.

var font := "mainmenu":
	set(value):
		font = value
		_load()
		queue_redraw()
var text := "":
	set(value):
		text = value
		queue_redraw()
var tint := Color.WHITE:
	set(value):
		tint = value
		queue_redraw()
var text_scale := 1.0:
	set(value):
		text_scale = value
		queue_redraw()
var centered := false:
	set(value):
		centered = value
		queue_redraw()
var spacing := 0.0
var pitch := 0.0             # more than 0: every letter takes this much (a fixed width font), letters centred

var _picture: Texture2D
var _glyphs: Dictionary = {}
var _line := 38.0


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _ready() -> void:
	_load()


func _load() -> void:
	var info: Dictionary = Assets.json("fonts/" + font)
	_glyphs = info.get("glyphs", {})
	_line = float(info.get("line", 38.0))
	_picture = Assets.texture("fonts/" + font + ".png")


func width_of(line: String) -> float:
	var w := 0.0
	for c in line:
		w += _advance(c) + spacing
	return w * text_scale


func line_height() -> float:
	return _line * text_scale


func _advance(c: String) -> float:
	if pitch > 0.0:
		return pitch
	var g: Array = _glyphs.get(str(c.unicode_at(0)), [])
	if g.is_empty():
		return _line * 0.35
	# the letters are drawn about as wide as their rectangle (the dark edge overlaps the next one a little); the
	# stored advance is the least a narrow letter or a space moves on
	return maxf(float(g[4] - g[2]), float(g[1]))


func _draw() -> void:
	if _picture == null:
		_load()
	if _picture == null:
		return
	var y := 0.0
	for line in text.split("\n"):
		var x := -width_of(line) * 0.5 if centered else 0.0
		for c in line:
			var g: Array = _glyphs.get(str(c.unicode_at(0)), [])
			if not g.is_empty():
				var source := Rect2(g[2], g[3], g[4] - g[2], g[5] - g[3])
				if source.size.x > 0.0:
					var left := float(g[0]) if pitch <= 0.0 else (pitch - source.size.x) * 0.5
					draw_texture_rect_region(_picture, Rect2(x + left * text_scale, y,
							source.size.x * text_scale, source.size.y * text_scale), source, tint)
			x += (_advance(c) + spacing) * text_scale
		y += _line * text_scale
