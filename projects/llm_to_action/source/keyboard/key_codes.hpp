#ifndef __CROSS_PLATFORM_KEYCODE_TYPE_DEFINITION_HEADER__
#define __CROSS_PLATFORM_KEYCODE_TYPE_DEFINITION_HEADER__
#include <util2/C/platform.h>
#include <cstdint>
#if defined(UTIL2_OS_WINDOWS)
#   define WIN32_LEAN_AND_MEAN
#   include <Windows.h>
#   undef WIN32_LEAN_AND_MEAN
#elif defined(UTIL2_OS_LINUX)
#   include <linux/input.h> // pulls input-event-codes.h
#endif


enum class KeyCodeEnum : std::uint16_t {
#if defined(UTIL2_OS_WINDOWS)
    Escape        = VK_ESCAPE,
    Enter         = VK_RETURN,
    Tab           = VK_TAB,
    Backspace     = VK_BACK,
    Delete        = VK_DELETE,
    Insert        = VK_INSERT,
    Home          = VK_HOME,
    End           = VK_END,
    PageUp        = VK_PRIOR,
    PageDown      = VK_NEXT,
    Space         = VK_SPACE,
    LeftArrow     = VK_LEFT,
    UpArrow       = VK_UP,
    RightArrow    = VK_RIGHT,
    DownArrow     = VK_DOWN,

    // Modifiers
    LeftShift     = VK_LSHIFT,
    RightShift    = VK_RSHIFT,
    LeftControl   = VK_LCONTROL,
    RightControl  = VK_RCONTROL,
    LeftAlt       = VK_LMENU,
    RightAlt      = VK_RMENU,
    LeftSuper     = VK_LWIN,
    RightSuper    = VK_RWIN,

    // Function keys F1 … F24
    F1 = VK_F1, F2 = VK_F2, F3 = VK_F3, F4 = VK_F4,
    F5 = VK_F5, F6 = VK_F6, F7 = VK_F7, F8 = VK_F8,
    F9 = VK_F9, F10 = VK_F10, F11 = VK_F11, F12 = VK_F12,
    F13 = VK_F13, F14 = VK_F14, F15 = VK_F15, F16 = VK_F16,
    F17 = VK_F17, F18 = VK_F18, F19 = VK_F19, F20 = VK_F20,
    F21 = VK_F21, F22 = VK_F22, F23 = VK_F23, F24 = VK_F24,

    // Top‑row numbers
    D0 = '0', D1 = '1', D2 = '2', D3 = '3', D4 = '4',
    D5 = '5', D6 = '6', D7 = '7', D8 = '8', D9 = '9',

    // Alphabet
    A = 'A', B = 'B', C = 'C', D = 'D', E = 'E', F = 'F',
    G = 'G', H = 'H', I = 'I', J = 'J', K = 'K', L = 'L',
    M = 'M', N = 'N', O = 'O', P = 'P', Q = 'Q', R = 'R',
    S = 'S', T = 'T', U = 'U', V = 'V', W = 'W', X = 'X',
    Y = 'Y', Z = 'Z',

    // Symbols (OEM mappings)
    Minus         = VK_OEM_MINUS,
    Equal         = VK_OEM_PLUS,
    BracketLeft   = VK_OEM_4,
    BracketRight  = VK_OEM_6,
    Backslash     = VK_OEM_5,
    Semicolon     = VK_OEM_1,
    Quote         = VK_OEM_7,
    Comma         = VK_OEM_COMMA,
    Period        = VK_OEM_PERIOD,
    Slash         = VK_OEM_2,
    Grave         = VK_OEM_3,

    // Numpad
    Numpad0       = VK_NUMPAD0,  Numpad1       = VK_NUMPAD1,
    Numpad2       = VK_NUMPAD2,  Numpad3       = VK_NUMPAD3,
    Numpad4       = VK_NUMPAD4,  Numpad5       = VK_NUMPAD5,
    Numpad6       = VK_NUMPAD6,  Numpad7       = VK_NUMPAD7,
    Numpad8       = VK_NUMPAD8,  Numpad9       = VK_NUMPAD9,
    NumpadAdd     = VK_ADD,      NumpadSubtract= VK_SUBTRACT,
    NumpadMultiply= VK_MULTIPLY, NumpadDivide  = VK_DIVIDE,
    NumpadDecimal = VK_DECIMAL,  NumpadEnter   = VK_RETURN,

    // Multimedia
    VolumeMute    = VK_VOLUME_MUTE,
    VolumeDown    = VK_VOLUME_DOWN,
    VolumeUp      = VK_VOLUME_UP,
    MediaNext     = VK_MEDIA_NEXT_TRACK,
    MediaPrev     = VK_MEDIA_PREV_TRACK,
    MediaStop     = VK_MEDIA_STOP,
    MediaPlayPause= VK_MEDIA_PLAY_PAUSE,

    // reserved
    Unknown       = 0xFEFE,
    Any            = 0xFEFD

#elif defined(UTIL2_OS_LINUX)
    Escape        = KEY_ESC,
    Enter         = KEY_ENTER,
    Tab           = KEY_TAB,
    Backspace     = KEY_BACKSPACE,
    Delete        = KEY_DELETE,
    Insert        = KEY_INSERT,
    Home          = KEY_HOME,
    End           = KEY_END,
    PageUp        = KEY_PAGEUP,
    PageDown      = KEY_PAGEDOWN,
    Space         = KEY_SPACE,
    LeftArrow     = KEY_LEFT,
    UpArrow       = KEY_UP,
    RightArrow    = KEY_RIGHT,
    DownArrow     = KEY_DOWN,

    // Modifiers
    LeftShift     = KEY_LEFTSHIFT,
    RightShift    = KEY_RIGHTSHIFT,
    LeftControl   = KEY_LEFTCTRL,
    RightControl  = KEY_RIGHTCTRL,
    LeftAlt       = KEY_LEFTALT,
    RightAlt      = KEY_RIGHTALT,
    LeftSuper     = KEY_LEFTMETA,
    RightSuper    = KEY_RIGHTMETA,

    // Function keys
    F1  = KEY_F1,  F2  = KEY_F2,  F3  = KEY_F3,  F4  = KEY_F4,
    F5  = KEY_F5,  F6  = KEY_F6,  F7  = KEY_F7,  F8  = KEY_F8,
    F9  = KEY_F9,  F10 = KEY_F10, F11 = KEY_F11, F12 = KEY_F12,
    F13 = KEY_F13, F14 = KEY_F14, F15 = KEY_F15, F16 = KEY_F16,
    F17 = KEY_F17, F18 = KEY_F18, F19 = KEY_F19, F20 = KEY_F20,
    F21 = KEY_F21, F22 = KEY_F22, F23 = KEY_F23, F24 = KEY_F24,

    // Top‑row numbers (Linux keycodes differ from ASCII)
    D0 = KEY_0, 
    D1 = KEY_1, 
    D2 = KEY_2, 
    D3 = KEY_3, 
    D4 = KEY_4,
    D5 = KEY_5, 
    D6 = KEY_6, 
    D7 = KEY_7, 
    D8 = KEY_8, 
    D9 = KEY_9,

    // Alphabet
    A = KEY_A, B = KEY_B, C = KEY_C, D = KEY_D, E = KEY_E,
    F = KEY_F, G = KEY_G, H = KEY_H, I = KEY_I, J = KEY_J,
    K = KEY_K, L = KEY_L, M = KEY_M, N = KEY_N, O = KEY_O,
    P = KEY_P, Q = KEY_Q, R = KEY_R, S = KEY_S, T = KEY_T,
    U = KEY_U, V = KEY_V, W = KEY_W, X = KEY_X, Y = KEY_Y,
    Z = KEY_Z,

    // Symbols
    Minus          = KEY_MINUS,
    Equal          = KEY_EQUAL,
    BracketLeft    = KEY_LEFTBRACE,
    BracketRight   = KEY_RIGHTBRACE,
    Backslash      = KEY_BACKSLASH,
    Semicolon      = KEY_SEMICOLON,
    Quote          = KEY_APOSTROPHE,
    Comma          = KEY_COMMA,
    Period         = KEY_DOT,
    Slash          = KEY_SLASH,
    Grave          = KEY_GRAVE,

    // Numpad (Linux KP codes)
    Numpad0        = KEY_KP0,  
    Numpad1        = KEY_KP1,
    Numpad2        = KEY_KP2,  
    Numpad3        = KEY_KP3,
    Numpad4        = KEY_KP4,  
    Numpad5        = KEY_KP5,
    Numpad6        = KEY_KP6,  
    Numpad7        = KEY_KP7,
    Numpad8        = KEY_KP8,  
    Numpad9        = KEY_KP9,
    NumpadAdd      = KEY_KPPLUS,     
    NumpadSubtract = KEY_KPMINUS,
    NumpadMultiply = KEY_KPASTERISK, 
    NumpadDivide   = KEY_KPSLASH,
    NumpadDecimal  = KEY_KPDOT,      
    NumpadEnter    = KEY_KPENTER,

    // Multimedia
    VolumeMute     = KEY_MUTE,
    VolumeDown     = KEY_VOLUMEDOWN,
    VolumeUp       = KEY_VOLUMEUP,
    MediaNext      = KEY_NEXTSONG,
    MediaPrev      = KEY_PREVIOUSSONG,
    MediaStop      = KEY_STOPCD,
    MediaPlayPause = KEY_PLAYPAUSE,

    Unknown        = 0xFEFE,
    Any            = 0xFEFD
#endif
};

enum class KeyAction : std::uint16_t {
#if defined(UTIL2_OS_WINDOWS)
    PRESSED  = WM_KEYDOWN,
    RELEASED = WM_KEYUP,
    REPEATED = 0xAAAA,
    UNKNOWN  = 0xFEFE
#elif defined(UTIL2_OS_LINUX)
    /* https://www.kernel.org/doc/html/latest/input/event-codes.html#ev-key */
    PRESSED  = 1,
    RELEASED = 0,
    REPEATED = 2,
    UNKNOWN  = 0xFEFE
#endif
};



constexpr std::uint16_t keyCodeToInteger(KeyCodeEnum k) noexcept {
    return static_cast<std::uint16_t>(k);
}

inline const char* keyCodeToString(KeyCodeEnum key) noexcept;
inline bool        keyCodeIsDigit(
    KeyCodeEnum key, 
    bool        numPad = false
) noexcept;




inline const char* keyCodeToString(KeyCodeEnum key) noexcept {
    switch (key) {
        // ── Common ────────────────────────────
        case KeyCodeEnum::Escape:     return "Escape";
        case KeyCodeEnum::Enter:      return "Enter";
        case KeyCodeEnum::Tab:        return "Tab";
        case KeyCodeEnum::Backspace:  return "Backspace";
        case KeyCodeEnum::Delete:     return "Delete";
        case KeyCodeEnum::Insert:     return "Insert";
        case KeyCodeEnum::Home:       return "Home";
        case KeyCodeEnum::End:        return "End";
        case KeyCodeEnum::PageUp:     return "Page Up";
        case KeyCodeEnum::PageDown:   return "Page Down";
        case KeyCodeEnum::Space:      return "Space";
        case KeyCodeEnum::LeftArrow:  return "Left Arrow";
        case KeyCodeEnum::UpArrow:    return "Up Arrow";
        case KeyCodeEnum::RightArrow: return "Right Arrow";
        case KeyCodeEnum::DownArrow:  return "Down Arrow";

        // ── Modifiers ─────────────────────────
        case KeyCodeEnum::LeftShift:   return "Left Shift";
        case KeyCodeEnum::RightShift:  return "Right Shift";
        case KeyCodeEnum::LeftControl: return "Left Control";
        case KeyCodeEnum::RightControl:return "Right Control";
        case KeyCodeEnum::LeftAlt:     return "Left Alt";
        case KeyCodeEnum::RightAlt:    return "Right Alt";
        case KeyCodeEnum::LeftSuper:   return "Left Super";
        case KeyCodeEnum::RightSuper:  return "Right Super";

        // ── Function keys ─────────────────────
        case KeyCodeEnum::F1:  return "F1";   case KeyCodeEnum::F2:  return "F2";
        case KeyCodeEnum::F3:  return "F3";   case KeyCodeEnum::F4:  return "F4";
        case KeyCodeEnum::F5:  return "F5";   case KeyCodeEnum::F6:  return "F6";
        case KeyCodeEnum::F7:  return "F7";   case KeyCodeEnum::F8:  return "F8";
        case KeyCodeEnum::F9:  return "F9";   case KeyCodeEnum::F10: return "F10";
        case KeyCodeEnum::F11: return "F11";  case KeyCodeEnum::F12: return "F12";
        case KeyCodeEnum::F13: return "F13";  case KeyCodeEnum::F14: return "F14";
        case KeyCodeEnum::F15: return "F15";  case KeyCodeEnum::F16: return "F16";
        case KeyCodeEnum::F17: return "F17";  case KeyCodeEnum::F18: return "F18";
        case KeyCodeEnum::F19: return "F19";  case KeyCodeEnum::F20: return "F20";
        case KeyCodeEnum::F21: return "F21";  case KeyCodeEnum::F22: return "F22";
        case KeyCodeEnum::F23: return "F23";  case KeyCodeEnum::F24: return "F24";

        // ── Numbers (top row) ────────────────
        case KeyCodeEnum::D0: return "0"; case KeyCodeEnum::D1: return "1";
        case KeyCodeEnum::D2: return "2"; case KeyCodeEnum::D3: return "3";
        case KeyCodeEnum::D4: return "4"; case KeyCodeEnum::D5: return "5";
        case KeyCodeEnum::D6: return "6"; case KeyCodeEnum::D7: return "7";
        case KeyCodeEnum::D8: return "8"; case KeyCodeEnum::D9: return "9";

        // ── Alphabet ──────────────────────────
        case KeyCodeEnum::A: return "A"; case KeyCodeEnum::B: return "B";
        case KeyCodeEnum::C: return "C"; case KeyCodeEnum::D: return "D";
        case KeyCodeEnum::E: return "E"; case KeyCodeEnum::F: return "F";
        case KeyCodeEnum::G: return "G"; case KeyCodeEnum::H: return "H";
        case KeyCodeEnum::I: return "I"; case KeyCodeEnum::J: return "J";
        case KeyCodeEnum::K: return "K"; case KeyCodeEnum::L: return "L";
        case KeyCodeEnum::M: return "M"; case KeyCodeEnum::N: return "N";
        case KeyCodeEnum::O: return "O"; case KeyCodeEnum::P: return "P";
        case KeyCodeEnum::Q: return "Q"; case KeyCodeEnum::R: return "R";
        case KeyCodeEnum::S: return "S"; case KeyCodeEnum::T: return "T";
        case KeyCodeEnum::U: return "U"; case KeyCodeEnum::V: return "V";
        case KeyCodeEnum::W: return "W"; case KeyCodeEnum::X: return "X";
        case KeyCodeEnum::Y: return "Y"; case KeyCodeEnum::Z: return "Z";

        // ── Symbols ───────────────────────────
        case KeyCodeEnum::Minus:        return "Minus (-)";
        case KeyCodeEnum::Equal:        return "Equal (=)";
        case KeyCodeEnum::BracketLeft:  return "Bracket Left ([)";
        case KeyCodeEnum::BracketRight: return "Bracket Right (])";
        case KeyCodeEnum::Backslash:    return "Backslash (\\)";
        case KeyCodeEnum::Semicolon:    return "Semicolon (;)";
        case KeyCodeEnum::Quote:        return "Quote (')";
        case KeyCodeEnum::Comma:        return "Comma (,)";
        case KeyCodeEnum::Period:       return "Period (.)";
        case KeyCodeEnum::Slash:        return "Slash (/)";
        case KeyCodeEnum::Grave:        return "Grave (`)";

        // ── Numpad ────────────────────────────
        case KeyCodeEnum::Numpad0:        return "Numpad 0";
        case KeyCodeEnum::Numpad1:        return "Numpad 1";
        case KeyCodeEnum::Numpad2:        return "Numpad 2";
        case KeyCodeEnum::Numpad3:        return "Numpad 3";
        case KeyCodeEnum::Numpad4:        return "Numpad 4";
        case KeyCodeEnum::Numpad5:        return "Numpad 5";
        case KeyCodeEnum::Numpad6:        return "Numpad 6";
        case KeyCodeEnum::Numpad7:        return "Numpad 7";
        case KeyCodeEnum::Numpad8:        return "Numpad 8";
        case KeyCodeEnum::Numpad9:        return "Numpad 9";
        case KeyCodeEnum::NumpadAdd:      return "Numpad +";
        case KeyCodeEnum::NumpadSubtract: return "Numpad -";
        case KeyCodeEnum::NumpadMultiply: return "Numpad *";
        case KeyCodeEnum::NumpadDivide:   return "Numpad /";
        case KeyCodeEnum::NumpadDecimal:  return "Numpad .";
        // case KeyCode::NumpadEnter:    return "Numpad Enter";

        // ── Multimedia ────────────────────────
        case KeyCodeEnum::VolumeMute:      return "Volume Mute";
        case KeyCodeEnum::VolumeDown:      return "Volume Down";
        case KeyCodeEnum::VolumeUp:        return "Volume Up";
        case KeyCodeEnum::MediaNext:       return "Media Next Track";
        case KeyCodeEnum::MediaPrev:       return "Media Previous Track";
        case KeyCodeEnum::MediaStop:       return "Media Stop";
        case KeyCodeEnum::MediaPlayPause:  return "Media Play/Pause";

        default:
            return "Unknown KeyCode";
    }
}


inline bool keyCodeIsDigit(
    KeyCodeEnum key, 
    bool        numPad
) noexcept 
{
    switch(key) {
        case KeyCodeEnum::D0: 
        case KeyCodeEnum::D1:
        case KeyCodeEnum::D2: 
        case KeyCodeEnum::D3:
        case KeyCodeEnum::D4: 
        case KeyCodeEnum::D5:
        case KeyCodeEnum::D6: 
        case KeyCodeEnum::D7:
        case KeyCodeEnum::D8: 
        case KeyCodeEnum::D9:
        return numPad ? false : true;

        case KeyCodeEnum::Numpad0:
        case KeyCodeEnum::Numpad1:
        case KeyCodeEnum::Numpad2:
        case KeyCodeEnum::Numpad3:
        case KeyCodeEnum::Numpad4:
        case KeyCodeEnum::Numpad5:
        case KeyCodeEnum::Numpad6:
        case KeyCodeEnum::Numpad7:
        case KeyCodeEnum::Numpad8:
        case KeyCodeEnum::Numpad9:
        return numPad;

        default:
        return false;
        break;
    }
    return false;
}


#endif /* __CROSS_PLATFORM_KEYCODE_TYPE_DEFINITION_HEADER__ */
