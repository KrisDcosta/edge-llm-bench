import json, time, os

variants = ['Q2_K', 'Q3_K_M', 'Q4_K_S', 'Q4_K_M', 'Q5_K_M', 'Q6_K', 'Q8_0']
last = {}

while True:
    try:
        d = json.load(open('C:/Users/Kris/291_EAI/results/quality_scores.json'))
        done = {
            k.split(':')[1]: v
            for k, v in d.items()
            if 'x86_boolq' in k and v.get('status') == 'success'
        }
        if done != last:
            os.system('cls')
            print(f'BoolQ  {len(done)}/7 complete\n')
            print(f'{"Variant":<12} {"Accuracy":>10} {"Correct":>9}')
            print('-' * 35)
            for v in variants:
                if v in done:
                    r = done[v]
                    print(f'{v:<12} {str(r["accuracy_pct"]) + "%":>10} {str(r["correct"]) + "/100":>9}')
                else:
                    label = 'running...' if v == variants[len(done)] else 'waiting'
                    print(f'{v:<12} {label:>10}')
            if len(done) == 7:
                print('\nCOMPLETE')
                break
            last = done
    except Exception:
        pass
    time.sleep(15)
