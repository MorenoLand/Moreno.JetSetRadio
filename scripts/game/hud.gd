class_name Hud
extends Control
# The heads-up display of the PC release, laid out for a window 1125 pixels high (everything scales with the height):
# the bar at the top left (orange part = what is left, the rest dark blue), the "points" picture with the score in blue
# digits below it, and the time at the top right in orange digits with a dot between the seconds and the hundredths.
# The pictures are the ones of the game's HUD sheets (ui/game_1.png).

const SHEET := "ui/game_1.png"
const BAR_LEFT := 220.0
const BAR_TOP := 85.0
const BAR_WIDTH := 615.0
const BAR_HEIGHT := 36.0
const SLANT := 28.0
const BAR_FULL := 0.715            # the part of the bar a full tank fills
# orange digits 0 to 9, rectangles of the sheet in pixels (width 88, height 112 in the 512 x 512 picture)
const ORANGE := [
	Rect2(96, 352, 88, 112), Rect2(8, 128, 88, 112), Rect2(96, 128, 88, 112), Rect2(184, 128, 88, 112),
	Rect2(272, 128, 88, 112), Rect2(8, 240, 88, 112), Rect2(96, 240, 88, 112), Rect2(184, 240, 88, 112),
	Rect2(272, 240, 88, 112), Rect2(8, 352, 88, 112)]
const DOT := Rect2(247, 472, 24, 24)
const POINTS := Rect2(305, 355, 187, 75)

var health := 1.0
var score := 0
var cans := 0
var time_left := 0.0
var show_time := true

var _sheet: Texture2D


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)


func _ready() -> void:
	_sheet = Assets.texture(SHEET)


func _process(_delta: float) -> void:
	queue_redraw()


func _draw() -> void:
	if _sheet == null:
		return
	var u := size.y / 1125.0
	_bar(u)
	# "points" and the score
	draw_texture_rect_region(_sheet, Rect2(Vector2(665.0, 148.0) * u, POINTS.size * u * 1.12), POINTS)
	_teal_digits(str(score), Vector2(590.0 * u, 148.0 * u), u)
	if show_time:
		_time(u)
	# the spray cans the skater carries: the can of the sheet and the number
	draw_texture_rect_region(_sheet, Rect2(Vector2(60.0, 940.0) * u, Vector2(58.0, 104.0) * u * 0.9), Rect2(386, 0, 58, 104))
	_teal_digits(str(cans), Vector2(130.0 * u, 970.0 * u), u)


func _bar(u: float) -> void:
	var x := BAR_LEFT * u
	var y := BAR_TOP * u
	var w := BAR_WIDTH * u
	var h := BAR_HEIGHT * u
	var s := SLANT * u
	var dark := PackedVector2Array([Vector2(x + s, y), Vector2(x + w, y), Vector2(x + w - s, y + h), Vector2(x, y + h)])
	draw_colored_polygon(dark, Color(0.04, 0.05, 0.2, 0.95))
	var f := clampf(health, 0.0, 1.0) * BAR_FULL
	if f > 0.0:
		var fw := w * f
		var orange := PackedVector2Array([Vector2(x + s, y), Vector2(x + fw, y), Vector2(x + fw - s, y + h), Vector2(x, y + h)])
		draw_colored_polygon(orange, Color(1.0, 0.62, 0.0))


func _teal_digits(text: String, at: Vector2, u: float) -> void:
	# the first glyph is the octagon with the dash that stands for zero in this picture
	var x := at.x
	for c in text:
		var d := c.unicode_at(0) - 48
		if d < 0 or d > 9:
			continue
		var index := 9 if d == 0 else d - 1
		var cell := Rect2(12.0 + (index % 5) * 49.0, 10.0 + (index / 5) * 62.0, 49.0, 55.0)
		var target := Vector2(49.0, 55.0) * u * 1.15
		draw_texture_rect_region(_sheet, Rect2(Vector2(x, at.y), target), cell)
		x += target.x * 0.95


func _time(u: float) -> void:
	var total := maxi(int(round(maxf(time_left, 0.0) * 100.0)), 0)
	var seconds := total / 100
	var hundredths := total % 100
	var text := "%d" % seconds
	var scale := u
	var digit_w := 80.0 * scale
	var x := size.x * 0.738
	var y := 80.0 * u
	for c in text:
		_orange(c.unicode_at(0) - 48, Vector2(x, y), scale)
		x += digit_w
	draw_texture_rect_region(_sheet, Rect2(Vector2(x, y + 112.0 * scale - 22.0 * u), DOT.size * scale), DOT)
	x += DOT.size.x * scale * 1.1
	for c in "%02d" % hundredths:
		_orange(c.unicode_at(0) - 48, Vector2(x, y + 22.0 * u), scale * 0.8)
		x += digit_w * 0.8


func _orange(d: int, at: Vector2, scale: float) -> void:
	if d < 0 or d > 9:
		return
	var rect: Rect2 = ORANGE[d]
	draw_texture_rect_region(_sheet, Rect2(at, rect.size * scale), rect)
