#!/usr/bin/env python3
"""Terminal Tic-Tac-Toe: human O versus an unbeatable computer X."""

from __future__ import annotations

from math import inf

Board = list[str | None]
WIN_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)
MOVE_ORDER = (4, 0, 2, 6, 8, 1, 3, 5, 7)


def new_board() -> Board:
    return [None] * 9


def winner(board: Board) -> str | None:
    for a, b, c in WIN_LINES:
        if board[a] is not None and board[a] == board[b] == board[c]:
            return board[a]
    return None


def available_moves(board: Board) -> list[int]:
    return [index for index, mark in enumerate(board) if mark is None]


def display_board(board: Board) -> None:
    cells = [mark if mark is not None else str(i + 1) for i, mark in enumerate(board)]
    print(f"\n {cells[0]} | {cells[1]} | {cells[2]}")
    print("---+---+---")
    print(f" {cells[3]} | {cells[4]} | {cells[5]}")
    print("---+---+---")
    print(f" {cells[6]} | {cells[7]} | {cells[8]}\n")


def minimax(board: Board, computer_turn: bool, depth: int = 0) -> int:
    result = winner(board)
    if result == "X":
        return 10 - depth
    if result == "O":
        return depth - 10
    moves = available_moves(board)
    if not moves:
        return 0

    scores = []
    mark = "X" if computer_turn else "O"
    for index in moves:
        board[index] = mark
        scores.append(minimax(board, not computer_turn, depth + 1))
        board[index] = None
    return max(scores) if computer_turn else min(scores)


def choose_computer_move(board: Board) -> int:
    moves = available_moves(board)
    if not moves:
        raise ValueError("No moves are available")
    best_move, best_score = moves[0], -inf
    for index in MOVE_ORDER:
        if board[index] is not None:
            continue
        board[index] = "X"
        score = minimax(board, computer_turn=False, depth=1)
        board[index] = None
        if score > best_score:
            best_move, best_score = index, score
    return best_move


def read_human_move(board: Board) -> int:
    while True:
        raw = input("Choose an empty square (1–9): ").strip()
        try:
            move = int(raw) - 1
        except ValueError:
            print("Enter a number from 1 to 9.")
            continue
        if move not in range(9):
            print("Choose a number from 1 to 9.")
        elif board[move] is not None:
            print("That square is occupied. Choose an empty one.")
        else:
            return move


def play() -> None:
    board = new_board()
    board[4] = "X"  # Keep the original game's computer-first center opening.
    print("Tic-Tac-Toe — you are O; the computer is X.")

    while True:
        display_board(board)
        if winner(board) == "X":
            print("Computer wins.")
            return
        if not available_moves(board):
            print("It's a draw.")
            return

        board[read_human_move(board)] = "O"
        if winner(board) == "O":
            display_board(board)
            print("You win!")
            return
        if not available_moves(board):
            display_board(board)
            print("It's a draw.")
            return

        board[choose_computer_move(board)] = "X"
        print("Computer moved.")


if __name__ == "__main__":
    play()
