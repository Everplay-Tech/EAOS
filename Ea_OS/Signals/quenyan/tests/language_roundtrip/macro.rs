macro_rules! make_setter {
    ($name:ident, $field:ident) => {
        pub fn $name(&mut self, value: impl Into<String>) {
            self.$field = value.into();
        }
    };
}

pub struct Builder {
    title: String,
}

impl Builder {
    make_setter!(title, title);
}
