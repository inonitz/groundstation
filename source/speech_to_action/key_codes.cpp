#include "key_codes.hpp"


// key_name.hpp or append to key_codes.hpp


const char* keyCodeToString(KeyCode key) noexcept {
    switch (key) {
        // ── Common ────────────────────────────
        case KeyCode::Escape:     return "Escape";
        case KeyCode::Enter:      return "Enter";
        case KeyCode::Tab:        return "Tab";
        case KeyCode::Backspace:  return "Backspace";
        case KeyCode::Delete:     return "Delete";
        case KeyCode::Insert:     return "Insert";
        case KeyCode::Home:       return "Home";
        case KeyCode::End:        return "End";
        case KeyCode::PageUp:     return "Page Up";
        case KeyCode::PageDown:   return "Page Down";
        case KeyCode::Space:      return "Space";
        case KeyCode::LeftArrow:  return "Left Arrow";
        case KeyCode::UpArrow:    return "Up Arrow";
        case KeyCode::RightArrow: return "Right Arrow";
        case KeyCode::DownArrow:  return "Down Arrow";

        // ── Modifiers ─────────────────────────
        case KeyCode::LeftShift:   return "Left Shift";
        case KeyCode::RightShift:  return "Right Shift";
        case KeyCode::LeftControl: return "Left Control";
        case KeyCode::RightControl:return "Right Control";
        case KeyCode::LeftAlt:     return "Left Alt";
        case KeyCode::RightAlt:    return "Right Alt";
        case KeyCode::LeftSuper:   return "Left Super";
        case KeyCode::RightSuper:  return "Right Super";

        // ── Function keys ─────────────────────
        case KeyCode::F1:  return "F1";   case KeyCode::F2:  return "F2";
        case KeyCode::F3:  return "F3";   case KeyCode::F4:  return "F4";
        case KeyCode::F5:  return "F5";   case KeyCode::F6:  return "F6";
        case KeyCode::F7:  return "F7";   case KeyCode::F8:  return "F8";
        case KeyCode::F9:  return "F9";   case KeyCode::F10: return "F10";
        case KeyCode::F11: return "F11";  case KeyCode::F12: return "F12";
        case KeyCode::F13: return "F13";  case KeyCode::F14: return "F14";
        case KeyCode::F15: return "F15";  case KeyCode::F16: return "F16";
        case KeyCode::F17: return "F17";  case KeyCode::F18: return "F18";
        case KeyCode::F19: return "F19";  case KeyCode::F20: return "F20";
        case KeyCode::F21: return "F21";  case KeyCode::F22: return "F22";
        case KeyCode::F23: return "F23";  case KeyCode::F24: return "F24";

        // ── Numbers (top row) ────────────────
        case KeyCode::D0: return "0"; case KeyCode::D1: return "1";
        case KeyCode::D2: return "2"; case KeyCode::D3: return "3";
        case KeyCode::D4: return "4"; case KeyCode::D5: return "5";
        case KeyCode::D6: return "6"; case KeyCode::D7: return "7";
        case KeyCode::D8: return "8"; case KeyCode::D9: return "9";

        // ── Alphabet ──────────────────────────
        case KeyCode::A: return "A"; case KeyCode::B: return "B";
        case KeyCode::C: return "C"; case KeyCode::D: return "D";
        case KeyCode::E: return "E"; case KeyCode::F: return "F";
        case KeyCode::G: return "G"; case KeyCode::H: return "H";
        case KeyCode::I: return "I"; case KeyCode::J: return "J";
        case KeyCode::K: return "K"; case KeyCode::L: return "L";
        case KeyCode::M: return "M"; case KeyCode::N: return "N";
        case KeyCode::O: return "O"; case KeyCode::P: return "P";
        case KeyCode::Q: return "Q"; case KeyCode::R: return "R";
        case KeyCode::S: return "S"; case KeyCode::T: return "T";
        case KeyCode::U: return "U"; case KeyCode::V: return "V";
        case KeyCode::W: return "W"; case KeyCode::X: return "X";
        case KeyCode::Y: return "Y"; case KeyCode::Z: return "Z";

        // ── Symbols ───────────────────────────
        case KeyCode::Minus:        return "Minus (-)";
        case KeyCode::Equal:        return "Equal (=)";
        case KeyCode::BracketLeft:  return "Bracket Left ([)";
        case KeyCode::BracketRight: return "Bracket Right (])";
        case KeyCode::Backslash:    return "Backslash (\\)";
        case KeyCode::Semicolon:    return "Semicolon (;)";
        case KeyCode::Quote:        return "Quote (')";
        case KeyCode::Comma:        return "Comma (,)";
        case KeyCode::Period:       return "Period (.)";
        case KeyCode::Slash:        return "Slash (/)";
        case KeyCode::Grave:        return "Grave (`)";

        // ── Numpad ────────────────────────────
        case KeyCode::Numpad0:        return "Numpad 0";
        case KeyCode::Numpad1:        return "Numpad 1";
        case KeyCode::Numpad2:        return "Numpad 2";
        case KeyCode::Numpad3:        return "Numpad 3";
        case KeyCode::Numpad4:        return "Numpad 4";
        case KeyCode::Numpad5:        return "Numpad 5";
        case KeyCode::Numpad6:        return "Numpad 6";
        case KeyCode::Numpad7:        return "Numpad 7";
        case KeyCode::Numpad8:        return "Numpad 8";
        case KeyCode::Numpad9:        return "Numpad 9";
        case KeyCode::NumpadAdd:      return "Numpad +";
        case KeyCode::NumpadSubtract: return "Numpad -";
        case KeyCode::NumpadMultiply: return "Numpad *";
        case KeyCode::NumpadDivide:   return "Numpad /";
        case KeyCode::NumpadDecimal:  return "Numpad .";
        // case KeyCode::NumpadEnter:    return "Numpad Enter";

        // ── Multimedia ────────────────────────
        case KeyCode::VolumeMute:      return "Volume Mute";
        case KeyCode::VolumeDown:      return "Volume Down";
        case KeyCode::VolumeUp:        return "Volume Up";
        case KeyCode::MediaNext:       return "Media Next Track";
        case KeyCode::MediaPrev:       return "Media Previous Track";
        case KeyCode::MediaStop:       return "Media Stop";
        case KeyCode::MediaPlayPause:  return "Media Play/Pause";

        default:
            return "Unknown KeyCode";
    }
}


bool keyCodeIsDigit(KeyCode key, bool numPad) noexcept
{
    switch(key) {
        case KeyCode::D0: 
        case KeyCode::D1:
        case KeyCode::D2: 
        case KeyCode::D3:
        case KeyCode::D4: 
        case KeyCode::D5:
        case KeyCode::D6: 
        case KeyCode::D7:
        case KeyCode::D8: 
        case KeyCode::D9:
        return numPad ? false : true;

        case KeyCode::Numpad0:
        case KeyCode::Numpad1:
        case KeyCode::Numpad2:
        case KeyCode::Numpad3:
        case KeyCode::Numpad4:
        case KeyCode::Numpad5:
        case KeyCode::Numpad6:
        case KeyCode::Numpad7:
        case KeyCode::Numpad8:
        case KeyCode::Numpad9:
        return numPad;

        default:
        return false;
        break;
    }
    return false;
}
