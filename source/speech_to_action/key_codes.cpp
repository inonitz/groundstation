#include "key_codes.hpp"


// key_name.hpp or append to key_codes.hpp


const char* keyCodeToString(KeyCodeEnum key) noexcept {
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


bool keyCodeIsDigit(KeyCodeEnum key, bool numPad) noexcept
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
