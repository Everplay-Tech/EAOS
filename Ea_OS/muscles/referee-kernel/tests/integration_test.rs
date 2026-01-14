#![cfg(test)]

use proptest::prelude::*;

proptest! {
    #[test]
    fn capability_key_derivation(
        key in prop::array::uniform32(any::<u8>()),
        salt1 in any::<u64>(),
        salt2 in any::<u64>()
    ) {
        prop_assume!(salt1 != salt2);
        
        let derived1 = referee::capability::ChaosCapability::derive_child_key(&key, salt1);
        let derived2 = referee::capability::ChaosCapability::derive_child_key(&key, salt2);
        
        assert_ne!(derived1, derived2);
    }
}
