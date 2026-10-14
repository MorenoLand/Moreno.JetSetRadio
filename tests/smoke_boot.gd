extends SceneTree
# Loads every script of the project (a parse error shows up here) and the main scene, and checks that the scene builds.
# Run: redot --headless --path . -s res://tests/smoke_boot.gd


func _initialize() -> void:
	var failed := 0
	for path in _scripts("res://scripts"):
		if load(path) == null:
			push_error("%s did not load" % path)
			failed += 1
	var scene: PackedScene = load("res://scenes/main.tscn")
	if scene == null:
		push_error("scenes/main.tscn did not load")
		quit(1)
		return
	var main := scene.instantiate()
	root.add_child(main)
	await process_frame
	var ok := main.get_child_count() > 0 and failed == 0
	print("smoke_boot: ", "ok" if ok else "FAILED")
	quit(0 if ok else 1)


func _scripts(folder: String) -> Array:
	var found := []
	var dir := DirAccess.open(folder)
	if dir == null:
		return found
	for name in dir.get_files():
		if name.ends_with(".gd"):
			found.append(folder + "/" + name)
	for sub in dir.get_directories():
		found.append_array(_scripts(folder + "/" + sub))
	return found
