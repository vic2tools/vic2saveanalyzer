// Python's behaviour where the recorded answers depend on it: how it spells
// numbers (`fmt`), matches the mod reader's patterns (`re`), writes JSON
// (`json`) and joins paths (`path`).

pub mod fmt;
pub mod json;
pub mod num;
pub mod path;
pub mod re;
pub mod repr;
