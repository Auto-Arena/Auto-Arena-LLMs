from utils.candidate import Candidate
import jsonlines
from utils.prompts import need_extra_space_cats, need_extra_space_cats_zh
from utils.common_utils import word2token_en, word2token_zh


# Lincoln Douglas style debate

def save_history(history, debate_history_file):

    # if debate_history_file is not None and all_debate_history_file is not None:
    if debate_history_file is not None:
    
        # save history to own file
        with jsonlines.open(debate_history_file, 'a') as writer:
            writer.write(history)

def make_pair_debate(model_a, model_b, question, 
                     debate_history_file = None,
                     language = 'en',):
    '''
    Input:
        model_a: str, model name
        model_b: str, model name
        question: dict, question to debate
        debate_history_file: str, file to save debate history
    '''

    history = {
        'candidates': [model_a, model_b],
        'question': question,
        'gamekey': (question['id'], model_a, model_b),
        'num_rounds': 'LD',
        'rounds': [],
    }

    can_a = Candidate(model_a, question, language = language)
    can_b = Candidate(model_b, question, language = language)

    if language == 'en':
        word2token = word2token_en
    elif language == 'zh':
        word2token = word2token_zh
    if language == 'en' and question['domain'] in need_extra_space_cats:
        print('Adding extra space for domain:', question['domain'])
        max_tokens = int(400*word2token)
    elif language == 'en':
        max_tokens = int(300*word2token)
    elif language == 'zh' and question['domain'] in need_extra_space_cats_zh:
        print('为领域多加字数:', question['domain'])
        max_tokens = int(400*word2token)
    else:
        max_tokens = int(300*word2token)
    ############ ROUND 0 ############
    # a takes stance
    a_response_rnd1 = can_a.get_response(max_tokens = max_tokens)
    # b takes stance
    b_response_rnd1 = can_b.get_response(max_tokens = max_tokens)

    try:
        ############ ROUND 1 ############
        # b cross-examines a
        can_b.receive_opponent_response(a_response_rnd1['no_thought'], action_guide = ['<criticize>', '<raise>'])
        b_response = can_b.get_response(max_tokens = max_tokens)
        # a responds
        can_a.receive_opponent_response(b_response['no_thought'], action_guide = ['<respond>'])
        a_response = can_a.get_response(max_tokens = max_tokens)

        history['rounds'].append([('a', a_response_rnd1), 
                                ('b', b_response),
                                ('a', a_response)])

        ############ ROUND 2 ############
        # a cross-examines b
        can_a.receive_opponent_response(b_response_rnd1['no_thought'], action_guide = ['<criticize>', '<raise>'])
        a_response = can_a.get_response(max_tokens = max_tokens)
        # b responds
        can_b.receive_opponent_response(a_response['no_thought'], action_guide = ['<respond>'])
        b_response = can_b.get_response(max_tokens = max_tokens)

        history['rounds'].append([('b', b_response_rnd1),
                                    ('a', a_response),
                                    ('b', b_response)])
    except Exception as e:
        if hasattr(e, 'param') and e.param in ['max_tokens', 'security']:
            gamekey = history['gamekey']
            print(f'Encountered error in game [[{gamekey}]] round 2, exiting...')
            history['rounds'].append([('a', a_response_rnd1),
                                        ('b', b_response_rnd1)])
        
            # save_history(history, debate_history_file, all_debate_history_file)
            save_history(history, debate_history_file)
            return history
        else:
            raise e

    try:
        ############ ROUND 3 ############
        # a rebuttal
        can_a.receive_opponent_response(b_response['no_thought'], action_guide = ['<criticize>', '<raise>'])
        a_response = can_a.get_response(max_tokens = max_tokens)
        # b rebuttal
        can_b.receive_opponent_response(a_response['no_thought'], action_guide = ['<respond>', '<criticize>', '<raise>'])
        b_response = can_b.get_response(max_tokens = max_tokens*2)
        # a final response
        can_a.receive_opponent_response(b_response['no_thought'], action_guide = ['<respond>'])
        a_final_response = can_a.get_response(max_tokens = max_tokens)

        history['rounds'].append([('a', a_response),
                                ('b', b_response),
                                ('a', a_final_response)])
    except Exception as e:
        if hasattr(e, 'param') and e.param in ['max_tokens', 'security']:
            gamekey = history['gamekey']
            print(f'Encountered error in game [[{gamekey}]] round 3, exiting...')
            # save_history(history, debate_history_file, all_debate_history_file)
            save_history(history, debate_history_file)
            return history
        else:
            raise e
    
    save_history(history, debate_history_file)
    
    return history

