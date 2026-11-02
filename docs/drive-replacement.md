# FlashBlade Drive (DFM) Replacement

This document describes how failed DirectFlash Modules (DFMs) in our FlashBlade are replaced, and why it is safe to send the failed modules back to Everpure.

## Replacement Process

1. When a DFM fails, the FlashBlade automatically opens a support ticket with Pure. No action is needed from us to report the failure.
2. Pure support contacts us to request access to the data center so their staff can replace the DFM.
3. Hakan and/or Michael arrange data center access for the Pure support staff.
4. Pure support staff replace the failed DFM on site.
5. The failed DFM is returned to Everpure. We do not keep or destroy failed modules ourselves.

## Is It Safe to Return Failed DFMs?

Yes. A single DFM, or a single blade, does not contain any recoverable user data. From our Everpure contact:

> Failed DFMs would come back to Everpure after they are replaced. For a FlashBlade to boot and be able to access data on the blades, there need to be a quorum of blades in the array. The quorum is defined as "floor(n/2)+1" so a 10 blade system in your case would need 6 blades. No data is recoverable from any single blade or DFM. This has also been verified by a 3rd party to adhere to NIST 800-88r1 of data at rest for the removal of a single blade and the validation confirms that a single removed blade (due to upgrade, fault, theft, etc) contains no discernable user data.

In short, for our 10 blade FlashBlade:

- Data can only be accessed when a quorum of `floor(10/2)+1 = 6` blades is present.
- A single removed blade or DFM, whether replaced due to a fault, removed for an upgrade, or stolen, contains no discernible user data.
- This has been validated by a third party against NIST SP 800-88 Rev. 1 for data at rest.

The same information is available in Everpure's security FAQ: https://support.everpuredata.com/r/security-resources/faq-general-topics
