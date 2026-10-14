class_name Sound
extends Node
# Music and effects. One music voice, a few effect voices; streams are read from assets/audio as they are asked for.
#
# Which track belongs to which screen is partly known: the title starts BGM number 0x9D of the game's table of
# streams, which is ROCK_M. The garage and stage playlists are a choice, not data of the game (see docs/screens.md).

const MUSIC := "audio/music/"
const EFFECTS := "audio/sounds/"
const VOICES := 6

# the menu effects of the system bank, by what they are used for here (picked by length and position in the bank)
const MOVE := "sys_se_e_s000.ogg"
const CONFIRM := "sys_se_e_s010.ogg"
const BACK := "sys_se_e_s004.ogg"
const START := "sys_se_e_s012.ogg"

# the effects of the stage. The renders e_se000 to e_se018 turned out to be the events of the common bank (a dog, gunfire ...),
# not the skater's own sounds, so nothing is played for these until the right programs are found (see docs/screens.md).
const JUMP := "sfx/sfx_701bdd2a64.wav"   # provisional: sounds 7, 5, 1 and 6 of the character bank, picked by length
const LAND := "sfx/sfx_5ab2d630cb.wav"
const FALL := "sfx/sfx_8c573c9d2f.wav"
const BOOST := "sfx/sfx_4ed33103cf.wav"

static var main: Sound

var _music: AudioStreamPlayer
var _voices: Array = []
var _next := 0
var _cache: Dictionary = {}
var _playing := ""
var _playlist: Array = []
var _queue_index := 0


func _init() -> void:
	main = self
	_music = AudioStreamPlayer.new()
	add_child(_music)
	_music.finished.connect(_on_music_finished)
	for i in VOICES:
		var p := AudioStreamPlayer.new()
		add_child(p)
		_voices.append(p)


func _stream(relative: String) -> AudioStream:
	if _cache.has(relative):
		return _cache[relative]
	var path := Assets.path(relative)
	var stream: AudioStream = null
	if FileAccess.file_exists(path):
		stream = _load_wav(path) if path.ends_with(".wav") else AudioStreamOggVorbis.load_from_file(path)
	_cache[relative] = stream
	return stream


func _load_wav(path: String) -> AudioStreamWAV:
	# mono 16-bit files with the plain 44 byte header that tools/sosb.py writes
	var bytes := FileAccess.get_file_as_bytes(path)
	if bytes.size() <= 44:
		return null
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = bytes.decode_u32(24)
	stream.data = bytes.slice(44)
	return stream


func play_music(name: String, loop: bool = true) -> void:
	if _playing == name and _music.playing:
		return
	_playlist = []
	_start_music(name, loop)


func play_playlist(names: Array) -> void:
	# tracks one after the other, in the order given, then again
	_playlist = names.duplicate()
	_queue_index = 0
	if _playlist.is_empty():
		return
	_start_music(_playlist[0], false)


func stop_music() -> void:
	_playlist = []
	_playing = ""
	_music.stop()


func _start_music(name: String, loop: bool) -> void:
	var stream := _stream(MUSIC + name)
	if stream == null:
		_playing = ""
		_music.stop()
		return
	if stream is AudioStreamOggVorbis:
		stream.loop = loop
	_playing = name
	_music.stream = stream
	_music.play()


func _on_music_finished() -> void:
	if _playlist.is_empty():
		return
	_queue_index = (_queue_index + 1) % _playlist.size()
	_start_music(_playlist[_queue_index], false)


func effect(name: String) -> void:
	if name == "":
		return
	if name.begins_with("sfx/"):
		_play_stream(_stream("audio/" + name))
		return
	_play_stream(_stream(EFFECTS + name))


func voice(index: int) -> void:
	# the streams the game keeps in its voice slots: 0 is the "Jet Set Radio" call of the title screen
	_play_stream(_stream("audio/voices/voice_%d.ogg" % index))


func _play_stream(stream: AudioStream) -> void:
	if stream == null:
		return
	var player: AudioStreamPlayer = _voices[_next]
	_next = (_next + 1) % VOICES
	player.stream = stream
	player.play()


static func sfx(name: String) -> void:
	if main:
		main.effect(name)


static func call_voice(index: int) -> void:
	if main:
		main.voice(index)


static func music(name: String, loop: bool = true) -> void:
	if main:
		main.play_music(name, loop)


static func playlist(names: Array) -> void:
	if main:
		main.play_playlist(names)


static func silence() -> void:
	if main:
		main.stop_music()
