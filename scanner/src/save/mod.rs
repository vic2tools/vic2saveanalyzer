// Reading a save: its provinces and pops (`province`), its countries
// (`country`), a block as a generic tree (`clause`), the bytes' numbers and
// quotes (`text`), the names it meets (`names`), and a save not laid out the
// way the game writes it, token by token (`walk`).

pub mod clause;
pub mod country;
pub mod names;
pub mod province;
pub mod text;
pub mod walk;
