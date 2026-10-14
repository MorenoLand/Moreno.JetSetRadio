extends Control
# Start scene. Starts the game when exported assets are present (the model viewer with --viewer), otherwise says
# what to do.

const VIEWER := "res://scenes/viewer.tscn"
const GAME := "res://scripts/game/game.gd"


func _ready() -> void:
	if Assets.available():
		if OS.get_cmdline_user_args().has("--viewer"):
			add_child(load(VIEWER).instantiate())
		else:
			add_child(load(GAME).new())
		return
	var label := Label.new()
	label.set_anchors_preset(Control.PRESET_FULL_RECT)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.text = "Jet Set Radio\n\nNo assets found. See README.md."
	add_child(label)
