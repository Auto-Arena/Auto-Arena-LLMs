from utils.prompts import qgen_command_dict, qgen_example_dict, qgen_command_dict_zh, qgen_example_dict_zh
from utils.api_utils import chat_completion_openai
import jsonlines
from collections import defaultdict 
import os

domain_list = ['writing', 'roleplay', 'extraction', 'reasoning', 'math', 'coding', 'STEM knowledge', 'humanities/social science knowledge']
domain_list_zh = ['写作', '角色扮演', '信息提取', '推理', '数学', '编程', '理工/自然科学知识', '人文社科知识']

class Generator:
    def __init__(self, model_name='gpt-4-turbo-preview',
        question_file='data/generated_questions_medium_difficult.jsonl', 
        n_each_time=10,
        language = 'en'):
        
        # Currently points to gpt-4-turbo-2024-04-09.
        self.model_name = model_name
        self.language = language
        if language == 'en':
            self.domains = domain_list
            self.question_file = question_file
        elif language == 'zh':
            self.domains = domain_list_zh
            # don't overlap with previous debate questions
            if not question_file.endswith('_zh.jsonl'):
                self.question_file = question_file.replace('.jsonl', '_zh.jsonl')
        # how many questions do we ask LLM to generate in the prompt, set to 10
        self.n_each_time = n_each_time
        self.questions = []

    def get_prompt(self, domain: str, num: int):
        if self.language == 'en':
            prompt = f"""You have been assigned the task of drafting a set of {num} different user queries to a chat assistant on {domain}. Please strictly follow these 6 rules for the question: 
1. The question is likely for a user to ask in real life. Follow the format of the example query. {qgen_command_dict[domain]} 2. It can be answered by the chatbot itself without additional inputs. 3. You need to generate the queries as DIVERSIFED as possible. 4. DO NOT add other words other than the query itself. 5. The question should be complicated and difficult, requiring in-depth understanding and analysis of the subject.
Each question in one line, add the serial number in parenthesis (e.g., “(1).”, “(2).”) before each question. 
Example query: {qgen_example_dict[domain]}"""
        elif self.language == 'zh':
            prompt = f"""你被分配了一个任务，需要为一个的聊天助手起草一组关于{domain}的{num}个不同的用户查询问题。请严格遵守以下6条问题规则：
1. 问题是用户在现实生活中可能会提出的。请遵循示例问题的格式。{qgen_command_dict_zh[domain]} 2. 聊天机器人本身可以在不需要额外输入的情况下回答问题。 3. 您需要尽可能多样化地生成查询。4.请不要添加除了查询本身之外的其他词语。5.问题应该是复杂和困难的，需要对主题有深入的理解和分析。
每个问题一行，每个问题前加上括号中的序号（例如，“(1).”, “(2).”）。
示例问题：{qgen_example_dict_zh[domain]}"""
        return prompt

    def parse_questions(self, qs):
        #qs: a string with 1. to 10.
        questions_parsed = []
        for i in range(1, self.n_each_time+1):
            if i == self.n_each_time: #last one
                q = qs.split(f"({i}).")[1].strip()
            else:
                q = qs.split(f"({i}).")[1].split(f"({i+1}).")[0].strip()
            questions_parsed.append(q)
        return questions_parsed

    def generate_questions(self, num_each_domain_to_generate = 30):
        # num each domain: should be a multiple of n_each_time
        questions = {}
        for domain in self.domains:
            questions[domain] = []
            prompt = self.get_prompt(domain, self.n_each_time)
            sample_n = num_each_domain_to_generate//self.n_each_time
            message = [{"role": "system", "content": prompt}]
            all_responses = chat_completion_openai(self.model_name, message, temperature = 0.7, max_tokens = 3000, n = int(sample_n))
            if sample_n != 1:
                for r in all_responses:
                    questions[domain] += self.parse_questions(r)
            else:
                questions[domain] += self.parse_questions(all_responses)
        # save to jsonl file
        with jsonlines.open(self.question_file, 'w') as writer:
            i = 1
            for domain, qs in questions.items():
                for q in qs:
                    writer.write({'domain': domain, 'id': i, 'question': q})
                    i += 1
        self.questions = questions
        return questions
    
    def load_questions(self, num_each_domain_to_load = False):
        loaded_domain_num = defaultdict(lambda: 0)
        questions = []
        with jsonlines.open(self.question_file) as reader:
            for obj in reader:
                # if num_each_domain_to_load is False, load all questions
                if num_each_domain_to_load == False:
                    questions.append(obj)
                # if num_each_domain_to_load is a number, load that many questions per domain
                elif loaded_domain_num[obj['domain']] < num_each_domain_to_load:
                    questions.append(obj)
                    loaded_domain_num[obj['domain']] += 1
        self.questions = questions
        return questions
    
    def get_question(self, question_id:int):
        if self.questions == []:
            self.load_questions()
        return [q for q in self.questions if q['id'] == question_id][0]
    

def load_question_from_generator(question_save_file, num_each_domain_to_load, language = 'en'):
    gen = Generator(question_file=question_save_file, language = language)

    # generate if no questions
    if not os.path.exists(gen.question_file):
        gen.generate_questions(num_each_domain_to_generate=30)

    # load questions
    questions = gen.load_questions(num_each_domain_to_load = num_each_domain_to_load)
    print(f"Loaded {len(questions)} questions from {gen.question_file}")

    return questions

