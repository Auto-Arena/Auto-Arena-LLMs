from utils.api_utils import generate_response
from utils.prompts import candidate_instruction, action_prompts, action_prompts_writing, need_extra_space_cats
from utils.prompts import candidate_instruction_zh, action_prompts_zh, action_prompts_writing_zh, need_extra_space_cats_zh
from utils.common_utils import count_tokens
import re

actions_en_to_zh = {'<respond>': '<回答>', '<think>': '<思考>', '<criticize>': '<批评>', '<raise>': '<提问>'}
def action_list_in_language(actions, language):
    if language == 'en':
        return actions
    elif language == 'zh':
        return [actions_en_to_zh[a] for a in actions]

class Candidate:
    def __init__(self, model_name, initial_question, language = 'en'):

        self.model_name = model_name
        self.language = language
        if language == 'en':
            self.candidate_instruction = candidate_instruction
            self.action_prompts = action_prompts
            self.action_prompts_writing = action_prompts_writing
            self.need_extra_space_cats = need_extra_space_cats
        elif language == 'zh':
            self.candidate_instruction = candidate_instruction_zh
            self.action_prompts = action_prompts_zh
            self.action_prompts_writing = action_prompts_writing_zh
            self.need_extra_space_cats = need_extra_space_cats_zh

        if initial_question['domain'] in self.need_extra_space_cats:
            self.action_prompts = self.action_prompts_writing
        round1_actions = self.action_prompts['<respond>']
        q = initial_question['question']

        if language == 'zh':
            self.chat_history = [{"role": "system", "content":self.candidate_instruction},
                             {"role": "user", "content": f'{round1_actions}\n初始用户输入: {q}'}]
        elif language == 'en':
            self.chat_history = [{"role": "system", "content":self.candidate_instruction},
                                {"role": "user", "content": f'{round1_actions}\nInitial user input: {q}'}]
        self.actions = action_list_in_language(['<respond>'], language)

    def get_response(self, max_tokens):
        '''
        returns: 
            response (dict): {'original': str, 'no_thought': str, 'parsed': [(str, str)]}
        '''
        response = {}
        # generate response
        original_response = generate_response(self, self.chat_history, n=1, max_tokens=max_tokens)

        if original_response == '$ERROR$':
            raise Exception('Error in generating response')
        
        # parse response
        response['parsed'] = self.parse_response(original_response)
        response['no_thought'] = self.no_thought_content(response['parsed'])
        # response['original'] = self.reconstruct_response(response['parsed'])
        response['original'] = original_response

        # automatically append to chat history, can see own thoughts
        self.chat_history.append({"role": "assistant", "content": response['original']})
        
        # if actions in action guide is not done, try to generate them
        actions_done = [p[0] for p in response['parsed']]
        used_tokens = count_tokens(response['original'])
        actions_undone = [a for a in self.actions if a not in actions_done]
        try_count = 0
        
        # a gap of 10 tokens is meaningful for generating a next response
        while actions_undone != [] and try_count < 2 and used_tokens + 10 < max_tokens:
            print('model: ', self.model_name, 'actions_undone:', actions_undone)
            # generate missing action prompt
            if self.language == 'zh':
                tmp_chat_history = self.chat_history.copy() + [{"role": "user",
                            "content": f"只生成{', '.join(actions_undone)}! 用标签括起来!"}]
            elif self.language == 'en':
                tmp_chat_history = self.chat_history.copy() + [{"role": "user", 
                                "content": f"Only generate {', '.join(actions_undone)}! ENCLOSE THEM IN TAGS!"}]
            # generate response
            new_response = generate_response(self, tmp_chat_history, n=1, max_tokens=max_tokens-used_tokens)
            
            # parse
            new_response_parsed = self.parse_response(new_response)
            for p in new_response_parsed:
                response['parsed'] = self.append_action_to_parsed_list(response['parsed'], p[0], p[1])

            response['original'] += new_response
            # response['original'] = self.reconstruct_response(response['parsed'])
            response['no_thought'] = self.no_thought_content(response['parsed'])
            
            # append to chat history
            self.chat_history[-1]['content'] += response['original']
            
            # update undone actions
            actions_done = [p[0] for p in response['parsed']]
            actions_undone = [a for a in self.actions if a not in actions_done]
            try_count += 1
            used_tokens += count_tokens(new_response)
        return response
    
    def receive_opponent_response(self, opponent_response, action_guide):
        '''
        Input: action guide: [<action>], except <think> 
        '''
        self.actions = action_list_in_language(action_guide, self.language)
        action_guide_prompt = self.action_prompts['_'.join(action_guide)]
        # automatically append to chat history
        if self.language == 'en':
            self.chat_history.append({"role": "user", "content": f"{action_guide_prompt}\nOpponent\'s Response:\n{opponent_response}"})
        elif self.language == 'zh':
            self.chat_history.append({"role": "user", "content": f"{action_guide_prompt}\n对手的回答:\n{opponent_response}"})

    def append_action_to_parsed_list(self, parsed, action, content):
        # all actions (except think) should be used only once
        done_actions = [p[0] for p in parsed]
        # if action not in self.actions and action not in ['<think>', '<思考>']:
        #     print('Action not in action guide:', action)
        if action not in done_actions or (self.language == 'en' and action == '<think>') or (self.language == 'zh' and action == '<思考>'):
            # add to parsed
            parsed.append((action, content))
        else:
            # locate the last instance of the action
            for j in range(len(parsed)-1, -1, -1):
                if parsed[j][0] == action:
                    # replace it with the latest one
                    parsed[j] = (action, content)
                    break
        return parsed
    
    def reconstruct_response(self, parsed):
        response = ''
        for p in parsed:
            response += f'{p[0]}{p[1]}{p[0].replace("<", "</")}\n'
        return response

    def parse_response(self, response):
        # split response based on its respective tags
        if self.language == 'en':
            splitted = re.split(r'(<think>|</think>|<respond>|</respond>|<criticize>|</criticize>|<raise>|</raise>)', response)
        elif self.language == 'zh':
            splitted = re.split(r'(<思考>|</思考>|<回答>|</回答>|<批评>|</批评>|<提问>|</提问>)', response)
        parsed = []
        skip_next = False
        for i in range(len(splitted)):
            if skip_next:
                skip_next = False
                continue
            s = splitted[i]
            if s != '\n' and (any(c.isalpha() for c in s)): # contains letters
                if (self.language == 'en' and s in ['<think>', '<respond>', '<criticize>', '<raise>']) \
                    or (self.language == 'zh' and s in ['<思考>', '<回答>', '<批评>', '<提问>']):
                    self.append_action_to_parsed_list(parsed, s, splitted[i+1])
                    skip_next = True
                # if it was not enclosed in tags, regard it as a response
                elif (self.language == 'en' and s not in ['</think>', '</respond>', '</criticize>', '</raise>']):
                    self.append_action_to_parsed_list(parsed, '<respond>', s)
                elif (self.language == 'zh' and s not in ['</思考>', '</回答>', '</批评>', '</提问>']):
                    self.append_action_to_parsed_list(parsed, '<回答>', s)
        return parsed
    
    def no_thought_content(self, parsed):
        no_thought = ''
        for p in parsed:
            if (self.language == 'en' and p[0] in ['<respond>', '<raise>'])\
                or (self.language == 'zh' and p[0] in ['<回答>', '<提问>']):
                no_thought += f'{p[0]}{p[1]}{p[0].replace("<", "</")}\n'
        return no_thought
    
    def reformat_parsed(self, parsed):
        reformatted = ''
        for p in parsed:
            reformatted += f'{p[0]}{p[1]}{p[0].replace("<", "</")}\n'
        return reformatted