extends Screen
# What the game shows before the title: the rating screen, the intro film, the logo of the port. Timings are those of
# the PC release's boot tasks, in frames of 60 a second: a fade of 30 frames, 120 frames of rating screen, a logo that
# fades in over 25 frames, stays for 60 and fades out. A button skips the current step.

const FRAME := 1.0 / 60.0

var _backdrop: ColorRect
var _picture: TextureRect
var _fade: ColorRect
var _video: VideoStreamPlayer
var _step := 0
var _clock := 0.0
var _phase := 0
var _steps: Array = []
var _notice: Control


func _ready() -> void:
	Sound.silence()
	root_control.queue_free()
	root_control = Control.new()
	root_control.set_anchors_preset(Control.PRESET_FULL_RECT)
	root_control.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(root_control)
	_backdrop = ColorRect.new()
	_backdrop.set_anchors_preset(Control.PRESET_FULL_RECT)
	root_control.add_child(_backdrop)
	_picture = TextureRect.new()
	_picture.set_anchors_preset(Control.PRESET_FULL_RECT)
	_picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_picture.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	root_control.add_child(_picture)
	_video = VideoStreamPlayer.new()
	_video.set_anchors_preset(Control.PRESET_FULL_RECT)
	_video.expand = true
	_video.visible = false
	_video.finished.connect(_next_step)
	root_control.add_child(_video)
	_fade = ColorRect.new()
	_fade.set_anchors_preset(Control.PRESET_FULL_RECT)
	_fade.color = Color.BLACK
	_fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root_control.add_child(_fade)
	# the notice about graffiti: white letters on black, drawn in the 4:3 picture of the screens
	_notice = Control.new()
	_notice.set_anchors_preset(Control.PRESET_FULL_RECT)
	_notice.visible = false
	_notice.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root_control.add_child(_notice)
	var sheet := TextureRect.new()
	sheet.texture = Assets.texture("images/notice.png")
	sheet.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	sheet.stretch_mode = TextureRect.STRETCH_SCALE
	sheet.anchor_left = 0.16
	sheet.anchor_right = 0.795
	sheet.anchor_top = 0.062
	sheet.anchor_bottom = 0.933
	sheet.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_notice.add_child(sheet)
	root_control.move_child(_notice, _fade.get_index())
	# rating screen (black ground), the film, the notice, the logo of the port
	_steps = [
		{"kind": "picture", "file": "images/esrb.png", "ground": Color.BLACK, "hold": 120},
		{"kind": "video", "file": "videos/Heritage.ogv"},
		{"kind": "notice", "ground": Color.BLACK, "hold": 300},
		{"kind": "picture", "file": "images/blit_big.png", "ground": Color.BLACK, "hold": 60},
	]
	_begin_step()


func _begin_step() -> void:
	_clock = 0.0
	_phase = 0
	if _step >= _steps.size():
		finished.emit("title", {})
		set_process(false)
		return
	var info: Dictionary = _steps[_step]
	if info["kind"] == "video":
		var path := Assets.path(info["file"])
		if not FileAccess.file_exists(path):
			_next_step()
			return
		var stream := VideoStreamTheora.new()
		stream.file = path
		_video.stream = stream
		_video.visible = true
		_picture.visible = false
		_fade.color.a = 0.0
		_video.play()
		_phase = 9
	else:
		_video.visible = false
		_notice.visible = info["kind"] == "notice"
		_picture.visible = info["kind"] == "picture"
		if info["kind"] == "picture":
			_picture.texture = Assets.texture(info["file"])
		_backdrop.color = info["ground"]
		_fade.color.a = 1.0


func _next_step() -> void:
	_video.stop()
	_step += 1
	_begin_step()


func _process(delta: float) -> void:
	if _step >= _steps.size() or _phase == 9:
		return
	_clock += delta
	var hold := float(_steps[_step].get("hold", 60)) * FRAME
	var fade := 30.0 * FRAME
	match _phase:
		0:
			_fade.color.a = clampf(1.0 - _clock / fade, 0.0, 1.0)
			if _clock >= fade:
				_phase = 1
				_clock = 0.0
		1:
			if _clock >= hold:
				_phase = 2
				_clock = 0.0
		2:
			_fade.color.a = clampf(_clock / fade, 0.0, 1.0)
			if _clock >= fade:
				_next_step()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("confirm") or event.is_action_pressed("back"):
		_next_step()
