import time
from openai import OpenAI
import datetime
import pytz
import httpx

def count_tokens(text):
    return len(text.split())

def test_provider(provider_config, messages):

    provider_name = provider_config.get("name", "Unnamed Provider")
    log_content = []
    
    def log(message):
        log_content.append(message)
        # 返回当前消息以便实时显示
        return message
    
    first_log = log(f"开始测试服务商：{provider_name}")
    yield {"type": "log", "content": first_log}
    
    try:
        # 初始化客户端时添加 verify=False 参数
        client = OpenAI(
            api_key=provider_config["api_key"],
            base_url=provider_config["base_url"],
            http_client=httpx.Client(verify=False)  # 禁用 SSL 验证
        )

        # 初始化 token 计数器与文本变量
        reasoning_tokens = 0
        content_tokens = 0
        overall_tokens = 0
        final_usage = None  # 用于存储最终的usage信息

        reasoning_text = ""
        content_text = ""

        # 初始化计时变量
        start_time = time.time()
        first_token_time = None

        # 用于记录 reasoning 与 content 部分开始与结束的时刻
        reasoning_start_time = None
        reasoning_end_time = None
        content_start_time = None
        content_end_time = None

        # 发起流式请求
        response = client.chat.completions.create(
            model=provider_config["model"],
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )

        current_text = ""
        for chunk in response:
            if not chunk.choices:
                if chunk.usage:
                    usage_log = log(f"\n【Usage 信息】\n{chunk.usage}")
                    yield {"type": "log", "content": usage_log}
                    final_usage = chunk.usage  # 保存usage信息
                continue
            
            # 获取第一个 choice 的 delta
            delta = chunk.choices[0].delta
            # 尝试获取 reasoning 与 content 片段
            reasoning_piece = getattr(delta, 'reasoning_content', "")
            content_piece = getattr(delta, 'content', "")

            # 记录首个 token 到达时间（仅记录一次）
            if first_token_time is None and (reasoning_piece or content_piece):
                first_token_time = time.time() - start_time

            # 如果有 reasoning 内容
            if reasoning_piece:
                if reasoning_start_time is None:
                    reasoning_start_time = time.time()
                    yield {"type": "log", "content": "\n【推理过程】\n"}
                
                reasoning_text += reasoning_piece
                tokens = count_tokens(reasoning_piece)
                reasoning_tokens += tokens
                overall_tokens += tokens
                reasoning_end_time = time.time()
                
                # 实时输出推理内容
                yield {"type": "log", "content": reasoning_piece}

            # 如果有 content 内容
            elif content_piece:
                if content_start_time is None:
                    content_start_time = time.time()
                    yield {"type": "log", "content": "\n【生成内容】\n"}
                
                current_text += content_piece
                # 当遇到标点符号或累积一定长度时输出
                if any(p in content_piece for p in '，。！？、\n') or len(current_text) > 50:
                    content_log = log(current_text)
                    yield {"type": "log", "content": content_log}
                    current_text = ""
                
                content_text += content_piece
                tokens = count_tokens(content_piece)
                content_tokens += tokens
                overall_tokens += tokens
                content_end_time = time.time()

        total_time = time.time() - start_time
        reasoning_time = (reasoning_end_time - reasoning_start_time) if (reasoning_start_time and reasoning_end_time) else 0
        content_time = (content_end_time - content_start_time) if (content_start_time and content_end_time) else 0

        # 在输出测试指标前，使用final_usage更新token计数
        if final_usage:
            overall_tokens = final_usage.completion_tokens
            # 根据比例分配tokens
            total_length = len(reasoning_text) + len(content_text)
            if total_length > 0:
                reasoning_tokens = int(final_usage.completion_tokens * (len(reasoning_text) / total_length))
                content_tokens = final_usage.completion_tokens - reasoning_tokens

        # 如果还有未输出的文本
        if current_text:
            content_log = log(current_text)
            yield {"type": "log", "content": content_log}
        
        # 输出测试指标
        metrics_log = log(f"\n【{provider_name} 测试结果】")
        yield {"type": "log", "content": metrics_log}
        
        if first_token_time is not None:
            time_log = log(f"\n首 token 响应时间： {first_token_time:.2f} 秒")
            yield {"type": "log", "content": time_log}
        else:
            no_token_log = log("\n未收到 token 响应。")
            yield {"type": "log", "content": no_token_log}
        
        speed_log = log(f"\nReasoning 部分： {reasoning_tokens} tokens, 用时： {reasoning_time:.2f} 秒, 生成速度： {reasoning_tokens / reasoning_time if reasoning_time > 0 else 0:.2f} tokens/s")
        yield {"type": "log", "content": speed_log}
        
        content_speed_log = log(f"\nContent 部分： {content_tokens} tokens, 用时： {content_time:.2f} 秒, 生成速度： {content_tokens / content_time if content_time > 0 else 0:.2f} tokens/s")
        yield {"type": "log", "content": content_speed_log}
        
        overall_speed_log = log(f"\n总体生成： {overall_tokens} tokens, 总用时： {total_time:.2f} 秒, 生成速度： {overall_tokens / total_time if total_time > 0 else 0:.2f} tokens/s")
        yield {"type": "log", "content": overall_speed_log}
        
        separator_log = log("\n---------------------------\n")
        yield {"type": "log", "content": separator_log}

        # 最后返回完整结果
        yield {
            "type": "result",
            "data": {
                "provider": provider_name,
                "first_token_time": first_token_time,
                "reasoning_tokens": reasoning_tokens,
                "reasoning_time": reasoning_time,
                "content_tokens": content_tokens,
                "content_time": content_time,
                "overall_tokens": overall_tokens,
                "total_time": total_time,
                "log_content": "\n".join(log_content)
            }
        }
        
    except Exception as e:
        error_log = log(f"服务商 {provider_name} 测试过程中发生错误：{e}")
        yield {"type": "log", "content": error_log}
        yield {"type": "error", "content": str(e)}
