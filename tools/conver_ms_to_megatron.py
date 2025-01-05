from collections import OrderedDict
import numpy as np
from pathlib import Path
import torch
import sys
import os

MAIN_DIR = os.path.abspath(
    os.path.join(
        os.path.join(
            os.path.dirname(__file__), os.path.pardir
        ), os.path.pardir
    )
)
sys.path.append(MAIN_DIR)


# The pt file in ckpt_path is generated by
# examples/pretrain_gpt_rope_7b_test.sh
ckpt_path = Path(
    '/userhome/model/wanli/pretrain-gpt-rope-7B-test/iter_0000001/mp_rank_00/model_optim_rng.pt')
ckpt_path = Path(
    '/raid0/hjrong/tmp/pretrain-gpt-rope-7B-test/iter_0000001/mp_rank_00/model_optim_rng.pt')

ms_npy_base_path = Path('/userhome/tmp/7B')

pt_save_path = ms_npy_base_path / 'pt-ckpt' / 'iter_0000001' / 'mp_rank_00'
pt_save_path.mkdir(exist_ok=True, parents=True)
last_iter_file = f'{pt_save_path.parent.parent}/latest_checkpointed_iteration.txt'
with open(last_iter_file,'w') as f:
    f.write(1)

# load pt
pt_dict = torch.load(ckpt_path, map_location=torch.device('cpu'))

args_7B = {'bf16': False,
 'fp16': True,
 'num_layers': 32,
 'encoder_num_layers': 32,
 'seq_length': 4096,
 'encoder_seq_length': 4096,
 'max_position_embeddings': 4096,
 'hidden_size': 4096,
 'ffn_hidden_size': 10880,
 'make_vocab_size_divisible_by': 128,
 'micro_batch_size': 1,
 'num_attention_heads': 32,
 'use_rotary_position_embeddings': True,
 'ms_fast_gelu': False,
 'add_position_embedding':False,
 'padded_vocab_size': 125952}

args_200B = {'bf16': False,
 'fp16': True,
 'num_layers': 103,
 'encoder_num_layers': 103,
 'seq_length': 2048,
 'encoder_seq_length': 2048,
 'max_position_embeddings': 2048,
 'hidden_size': 12672,
 'ffn_hidden_size': 50688,
 'make_vocab_size_divisible_by': 64,
 'micro_batch_size': 1,
 'num_attention_heads': 96,
 'use_rotary_position_embeddings': True,
 'ms_fast_gelu': True,
 'add_position_embedding':False,
 'padded_vocab_size': 49984}

args = args_7B

for name in args:
    setattr(pt_dict['args'], name, args[name])

print(pt_dict['args'])
print(pt_dict['model']['language_model']['encoder'].keys())

language_model = pt_dict['model']['language_model']

npy_data = np.load(ms_npy_base_path / 'merged_ckpt.npy', allow_pickle=True)
loaded = {}
for i in npy_data:
    print(i['name'])
    loaded[i['name']] = torch.from_numpy(i['data'])


num_head = args['num_attention_heads']
hidden_size = args['hidden_size']
hp = hidden_size // num_head

new_sd = OrderedDict()
for layer_i in range(args['num_layers']):
    new_sd[f'layers.{layer_i}.input_layernorm.weight'] = loaded[f"backbone.blocks.{layer_i}.layernorm1.gamma"]
    new_sd[f'layers.{layer_i}.input_layernorm.bias'] = loaded[f"backbone.blocks.{layer_i}.layernorm1.beta"]

    q_w = loaded[f"backbone.blocks.{layer_i}.attention.dense1.weight"].view(
        *[-1, hp, hidden_size])
    k_w = loaded[f"backbone.blocks.{layer_i}.attention.dense2.weight"].view(
        *[-1, hp, hidden_size])
    v_w = loaded[f"backbone.blocks.{layer_i}.attention.dense3.weight"].view(
        *[-1, hp, hidden_size])
    new_sd[f'layers.{layer_i}.self_attention.query_key_value.weight'] = \
        torch.cat((q_w, k_w, v_w), dim=-2).view(*[3 * hidden_size, hidden_size])

    q_b = loaded[f"backbone.blocks.{layer_i}.attention.dense1.bias"].view(
        *[-1, hp])
    k_b = loaded[f"backbone.blocks.{layer_i}.attention.dense2.bias"].view(
        *[-1, hp])
    v_b = loaded[f"backbone.blocks.{layer_i}.attention.dense3.bias"].view(
        *[-1, hp])
    new_sd[f'layers.{layer_i}.self_attention.query_key_value.bias'] = \
        torch.cat((q_b, k_b, v_b), dim=-1).view(*[hidden_size * 3])

    new_sd[f'layers.{layer_i}.self_attention.dense.weight'] = loaded[f"backbone.blocks.{layer_i}.attention.projection.weight"].T
    new_sd[f'layers.{layer_i}.self_attention.dense.bias'] = loaded[f"backbone.blocks.{layer_i}.attention.projection.bias"]
    new_sd[f'layers.{layer_i}.post_attention_layernorm.weight'] = loaded[f"backbone.blocks.{layer_i}.layernorm2.gamma"]
    new_sd[f'layers.{layer_i}.post_attention_layernorm.bias'] = loaded[f"backbone.blocks.{layer_i}.layernorm2.beta"]
    new_sd[f'layers.{layer_i}.mlp.dense_h_to_4h.weight'] = loaded[f"backbone.blocks.{layer_i}.output.mapping.weight"].T
    new_sd[f'layers.{layer_i}.mlp.dense_h_to_4h.bias'] = loaded[f"backbone.blocks.{layer_i}.output.mapping.bias"]
    new_sd[f'layers.{layer_i}.mlp.dense_4h_to_h.weight'] = loaded[f"backbone.blocks.{layer_i}.output.projection.weight"].T
    new_sd[f'layers.{layer_i}.mlp.dense_4h_to_h.bias'] = loaded[f"backbone.blocks.{layer_i}.output.projection.bias"]

new_sd[f'final_layernorm.weight'] = loaded["backbone.layernorm.gamma"]
new_sd[f'final_layernorm.bias'] = loaded["backbone.layernorm.beta"]
language_model['encoder'] = new_sd

language_model['embedding']['word_embeddings'] = OrderedDict(
    {'weight': loaded["backbone.embedding.word_embedding.embedding_table"]})
language_model['embedding']['position_embeddings'] = OrderedDict(
    {'weight': loaded["backbone.embedding.word_embedding.embedding_table"]})
language_model['embedding']['position_embeddings'] = None


torch.save(pt_dict, pt_save_path / 'model_optim_rng.pt')

print('finish')
