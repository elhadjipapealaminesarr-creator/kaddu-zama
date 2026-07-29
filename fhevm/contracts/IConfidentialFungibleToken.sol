// SPDX-License-Identifier: BSD-3-Clause-Clear
pragma solidity ^0.8.24;

import {euint64, externalEuint64} from "@fhevm/solidity/lib/FHE.sol";

/// @title IConfidentialFungibleToken — minimal ERC-7984 surface used by Kaddu
/// @notice ERC-7984 is the confidential fungible token standard (OpenZeppelin
///         Confidential Contracts / Confidential Token Association). Balances and
///         transfer amounts are FHE ciphertext handles (euint64), never public.
///         Kaddu uses it to hold bid deposits and the winning payment in escrow
///         (e.g. a confidential stablecoin such as cUSDC / cUSDT).
/// @dev    This is a trimmed interface — only the members KadduTender needs.
interface IConfidentialFungibleToken {
    /// @notice Encrypted balance handle of `account`.
    function confidentialBalanceOf(address account) external view returns (euint64);

    /// @notice Grant/revoke `operator` the right to move the caller's tokens.
    ///         Required so the escrow contract can pull a bidder's deposit.
    function setOperator(address operator, uint48 until) external;

    /// @notice True if `operator` may currently move `holder`'s tokens.
    function isOperator(address holder, address operator) external view returns (bool);

    /// @notice Pull an encrypted `amount` from `from` to `to` (operator flow).
    ///         `from` must have called setOperator(msg.sender, ...) first.
    /// @return transferred The amount actually moved (clamped to the balance).
    function confidentialTransferFrom(
        address from,
        address to,
        externalEuint64 amount,
        bytes calldata inputProof
    ) external returns (euint64 transferred);

    /// @notice Send an encrypted `amount` already held by this contract to `to`.
    /// @return transferred The amount actually moved (clamped to the balance).
    function confidentialTransfer(address to, euint64 amount) external returns (euint64 transferred);
}
