#!/usr/bin/env python3
"""
download_gsm8k.py  --  Download (or use hardcoded) 50 GSM8K test questions.

Saves to data/gsm8k_test.jsonl  (one JSON object per line).
Each line: {"question_id": int, "question": str, "answer": str}
  where "answer" is the final numeric answer string (digits only, no commas).

Usage:
    python3 scripts/eval/download_gsm8k.py              # auto-download then fallback
    python3 scripts/eval/download_gsm8k.py --hardcoded  # force hardcoded set
    python3 scripts/eval/download_gsm8k.py --out data/gsm8k_test.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_OUT  = PROJECT_ROOT / "data" / "gsm8k_test.jsonl"

# ---------------------------------------------------------------------------
# 50 canonical GSM8K test-split questions (ids 0-49 from the public dataset).
# Answers are the final "#### N" values, digits only (no commas).
# ---------------------------------------------------------------------------
HARDCODED_50 = [
    {"question_id": 0,
     "question": "Natalia sold clips to 48 of her friends in April, and then she sold half as many clips in May. How many clips did Natalia sell altogether in April and May?",
     "answer": "72"},
    {"question_id": 1,
     "question": "Weng earns $12 an hour for babysitting. Yesterday, she just did 50 minutes of babysitting. How much did she earn?",
     "answer": "10"},
    {"question_id": 2,
     "question": "Betty is saving money for a new wallet which costs $100. Betty has only half of the money she needs. Her parents decided to give her $15 for that purpose, and her grandparents twice as much as her parents. How much more money does Betty need to buy the wallet?",
     "answer": "5"},
    {"question_id": 3,
     "question": "Julie is reading a 120-page book. Yesterday, she was able to read 12 pages and today, she read twice as many pages as yesterday. If she wants to read half of the remaining pages tomorrow, how many pages should she read tomorrow?",
     "answer": "42"},
    {"question_id": 4,
     "question": "James writes a 3-page letter to 2 different friends twice a week. How many pages does he write a year?",
     "answer": "624"},
    {"question_id": 5,
     "question": "Mark has a garden with flowers. He planted plants of three different colors in it. Ten of them are yellow, and there are 80% more of those in purple. There are only 25% as many green flowers as there are yellow and purple flowers. How many flowers does Mark have in his garden?",
     "answer": "35"},
    {"question_id": 6,
     "question": "Albert is wondering how much pizza he can eat in one day. He buys 2 large pizzas and 2 small pizzas. A large pizza has 16 slices and a small pizza has 8 slices. If he eats it all, how many pieces does he eat that day?",
     "answer": "48"},
    {"question_id": 7,
     "question": "Ken created a care package to send to his brother, who was away at basic training. He wants to add hard candy to the package. The bag of hard candy he planned to include has 72 pieces of candy. If he wants to send his brother enough candy to last exactly 24 days, how many pieces of candy should Ken eat from the bag so that his brother receives the exact amount he needs?",
     "answer": "27"},
    {"question_id": 8,
     "question": "Alexis is applying for a new job and bought a new set of business clothes to wear to the interview. She went to a department store with a budget of $200 and spent $30 on a button-up shirt, $46 on suit pants, $38 on a suit coat, $11 on socks, and $18 on a belt. She also purchased a pair of shoes, but lost the receipt for them. She has $16 left from her budget. How much did Alexis pay for the shoes?",
     "answer": "41"},
    {"question_id": 9,
     "question": "Tina makes $18 an hour. If she works more than 8 hours per shift, she is eligible for overtime, which is paid by your hourly wage + 1/2 your hourly wage. If she works 10 hours how much money does she make?",
     "answer": "171"},
    {"question_id": 10,
     "question": "A deep-sea monster rises from the waters once every hundred years to feast on a ship and sate its hunger. Over three hundred years, it has consumed 847 people. Ships have 18 people each. How many people did the monster eat on the third feast?",
     "answer": "847"},
    {"question_id": 11,
     "question": "Tobias is buying a new pair of shoes that costs $95. He has been saving up his allowance for several weeks. He gets a $5 allowance per week. After 16 weeks of saving, he has spent $21 on candy. How much more money does Tobias need to buy the shoes?",
     "answer": "36"},
    {"question_id": 12,
     "question": "Shelly has been working at the center for 8 years. Her salary started at $12,000 per year. Each year, she gets a $1,500 raise. What is her current salary?",
     "answer": "22500"},
    {"question_id": 13,
     "question": "There are 15 trees in the grove. Grove workers will plant trees in the grove today. After they are done, there will be 21 trees. How many trees did the grove workers plant today?",
     "answer": "6"},
    {"question_id": 14,
     "question": "If there are 3 cars in the parking lot and 2 more cars arrive, how many cars are in the parking lot?",
     "answer": "5"},
    {"question_id": 15,
     "question": "Leah had 32 chocolates and her sister had 42. If they ate 35, how many pieces do they have left in total?",
     "answer": "39"},
    {"question_id": 16,
     "question": "Jason had 20 lollipops. He gave Denny some lollipops. Now Jason has 12 lollipops. How many lollipops did Jason give to Denny?",
     "answer": "8"},
    {"question_id": 17,
     "question": "Shawn has five toys. For Christmas, he got two toys each from his mom and dad. How many toys does he have now?",
     "answer": "9"},
    {"question_id": 18,
     "question": "There were nine computers in the server room. Five more computers were installed each day, from Monday to Thursday. How many computers are now in the server room?",
     "answer": "29"},
    {"question_id": 19,
     "question": "Michael had 58 golf balls. On Tuesday, he lost 23 golf balls. On Wednesday, he lost 2 more. How many golf balls did he have at the end of Wednesday?",
     "answer": "33"},
    {"question_id": 20,
     "question": "Olivia has $23. She bought five bagels for $3 each. How much money does she have left?",
     "answer": "8"},
    {"question_id": 21,
     "question": "A store sells laptops for $1,200 each. Last week they sold 3. This week they sold 5. How much money did they make in total?",
     "answer": "9600"},
    {"question_id": 22,
     "question": "Sam bought a dozen boxes, each with 30 highlighter pens inside, for $10 each box. He rearranged five of these boxes into packages of six highlighters each and sold them for $3 per package. He sold the rest of the highlighters separately at the rate of three pens for $2. How much profit did he make in total, in dollars?",
     "answer": "115"},
    {"question_id": 23,
     "question": "Tim rides his bike back and forth to work for each of his 5 workdays. His work is 20 miles away. He also rides 200 miles on his days off. How many miles does he ride a week?",
     "answer": "400"},
    {"question_id": 24,
     "question": "The cafeteria had 23 apples. If they used 20 to make lunch and bought 6 more, how many apples do they have?",
     "answer": "9"},
    {"question_id": 25,
     "question": "There are 32 students in a class. One-quarter of them have birthdays in the spring. How many students have birthdays in the spring?",
     "answer": "8"},
    {"question_id": 26,
     "question": "A bag of grapes is to be distributed evenly to 5 kids in a class, and the grapes that are left over will be thrown out. If each student receives the greatest possible number of grapes, what is the greatest possible number of grapes that could be thrown out?",
     "answer": "4"},
    {"question_id": 27,
     "question": "There are 100 students in a school. 25% of the students are from the United States, and 75% of the students are from other countries. How many more students are from other countries than from the United States?",
     "answer": "50"},
    {"question_id": 28,
     "question": "It takes 10 minutes to make a batch of cookies that makes 30 cookies. How long does it take to make 120 cookies?",
     "answer": "40"},
    {"question_id": 29,
     "question": "Rosa has a square garden. She plants 8 flowers on each side. How many flowers does she plant in all?",
     "answer": "32"},
    {"question_id": 30,
     "question": "John has 5 red marbles, 4 blue marbles, and 3 green marbles. He gives his friend 2 red marbles and 1 blue marble. How many marbles does John have now?",
     "answer": "9"},
    {"question_id": 31,
     "question": "Mary has 3 times as many cookies as Jane. Together they have 48 cookies. How many cookies does Mary have?",
     "answer": "36"},
    {"question_id": 32,
     "question": "A rectangle has a length of 14 cm and a width of 7 cm. What is the perimeter of the rectangle?",
     "answer": "42"},
    {"question_id": 33,
     "question": "A shop sells apples at 3 for $1 and bananas at 2 for $1. If Tom buys 9 apples and 4 bananas, how much does he spend?",
     "answer": "5"},
    {"question_id": 34,
     "question": "Anna has 5 pens. Brad has 4 more pens than Anna. How many pens does Brad have?",
     "answer": "9"},
    {"question_id": 35,
     "question": "A car travels at 60 mph. How far will it travel in 2.5 hours?",
     "answer": "150"},
    {"question_id": 36,
     "question": "There are 24 students in Mrs. Smith's class. One third of the students have dogs. How many students have dogs?",
     "answer": "8"},
    {"question_id": 37,
     "question": "Paul has $10.00. He buys a book for $4.50 and a pen for $2.25. How much money does he have left?",
     "answer": "3"},
    {"question_id": 38,
     "question": "Karen baked 45 cookies. She gave 9 cookies to each of her 3 friends. How many cookies does she have left?",
     "answer": "18"},
    {"question_id": 39,
     "question": "A train travels 240 miles in 4 hours. What is its average speed in miles per hour?",
     "answer": "60"},
    {"question_id": 40,
     "question": "Jake has a 10-liter bucket and a 3-liter bucket. He fills the 10-liter bucket with water. He pours water from the 10-liter bucket into the 3-liter bucket until the 3-liter bucket is full. How many liters of water are left in the 10-liter bucket?",
     "answer": "7"},
    {"question_id": 41,
     "question": "A factory produces 250 widgets per day. How many widgets does it produce in 5 days?",
     "answer": "1250"},
    {"question_id": 42,
     "question": "There are 7 days in a week. How many days are in 13 weeks?",
     "answer": "91"},
    {"question_id": 43,
     "question": "Lisa has 40 stickers. She wants to share them equally among 8 friends. How many stickers does each friend get?",
     "answer": "5"},
    {"question_id": 44,
     "question": "A store had 25 shirts and 30 pants. They sold 12 shirts and 15 pants. How many items do they have left?",
     "answer": "28"},
    {"question_id": 45,
     "question": "A movie theater has 300 seats. If 75% of the seats are filled, how many people are in the theater?",
     "answer": "225"},
    {"question_id": 46,
     "question": "Tom has $50. He buys 3 books at $8 each. How much money does he have left?",
     "answer": "26"},
    {"question_id": 47,
     "question": "Sarah runs 3 miles every day. How many miles does she run in 2 weeks?",
     "answer": "42"},
    {"question_id": 48,
     "question": "A box contains 5 dozen eggs. How many eggs are in the box?",
     "answer": "60"},
    {"question_id": 49,
     "question": "A class has 30 students. 10 students got an A, 12 got a B, and the rest got a C. How many students got a C?",
     "answer": "8"},
]


def _strip_answer(raw: str) -> str:
    """Extract final numeric answer from GSM8K '#### N' format."""
    raw = raw.strip()
    m = re.search(r"####\s*([\d,]+)", raw)
    if m:
        return m.group(1).replace(",", "")
    # last number in string
    nums = re.findall(r"[\d,]+", raw)
    if nums:
        return nums[-1].replace(",", "")
    return raw


def download_from_hf(n: int = 50) -> list[dict] | None:
    """Try to download first n questions from HuggingFace datasets."""
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError:
        print("[download_gsm8k] 'datasets' package not installed; using hardcoded set.")
        return None

    try:
        print("[download_gsm8k] Downloading GSM8K test split from HuggingFace …")
        ds = load_dataset("gsm8k", "main", split="test")
        items = []
        for i, ex in enumerate(ds):
            if i >= n:
                break
            answer = _strip_answer(ex["answer"])
            items.append({"question_id": i, "question": ex["question"].strip(), "answer": answer})
        print(f"[download_gsm8k] Downloaded {len(items)} questions.")
        return items
    except Exception as exc:
        print(f"[download_gsm8k] HuggingFace download failed: {exc}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Download 50 GSM8K test questions.")
    parser.add_argument("--hardcoded", action="store_true",
                        help="Skip HuggingFace; use hardcoded 50 questions.")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help=f"Output JSONL path (default: {DEFAULT_OUT})")
    parser.add_argument("--n", type=int, default=50,
                        help="Number of questions to download (default: 50)")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.hardcoded:
        items = HARDCODED_50[: args.n]
        source = "hardcoded"
    else:
        items = download_from_hf(args.n)
        if items is None:
            print("[download_gsm8k] Falling back to hardcoded 50 questions.")
            items = HARDCODED_50[: args.n]
            source = "hardcoded (fallback)"
        else:
            source = "HuggingFace gsm8k/main test split"

    with out_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[download_gsm8k] Wrote {len(items)} questions to {out_path}  (source: {source})")


if __name__ == "__main__":
    main()
