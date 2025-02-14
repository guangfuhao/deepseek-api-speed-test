from flask import Flask, render_template, jsonify, request, Response
from flask_migrate import Migrate
from test_api_speed import test_provider
import datetime
import pytz
from dotenv import load_dotenv
import os
from testrecords import db, TestRecord, TestSession
import logging
from logging.handlers import RotatingFileHandler
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test_records.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
migrate = Migrate(app, db)

# 创建所有数据库表
with app.app_context():
    db.create_all()

# 配置日志
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('应用启动')

load_dotenv()

def get_provider_config(prefix, provider_name):
    """从环境变量获取服务商配置"""
    base_urls = {
        "DeepSeek 官方": "https://api.deepseek.com/v1",
        "阿里云/百炼": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "硅基流动Pro": "https://api.siliconflow.cn/v1",
        "硅基流动普通版": "https://api.siliconflow.cn/v1",
        "火山引擎": "https://ark.cn-beijing.volces.com/api/v3",
        "腾讯云": "https://api.lkeap.cloud.tencent.com/v1"
    }
    
    models = {
        "DeepSeek 官方": "deepseek-reasoner",
        "阿里云/百炼": "deepseek-r1",
        "硅基流动Pro": "Pro/deepseek-ai/DeepSeek-R1",
        "硅基流动普通版": "deepseek-ai/DeepSeek-R1",
        "火山引擎": os.getenv(f"{prefix}_deepseek-r1_model_name"),
        "腾讯云": "deepseek-r1"
    }
    
    api_key = os.getenv(f"{prefix}_API_KEY")
    if not api_key:
        raise ValueError(f"未找到 {prefix}_API_KEY 环境变量")
        
    return {
        "name": provider_name,
        "api_key": api_key,
        "base_url": base_urls[provider_name],
        "model": models[provider_name],
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/providers')
def get_providers():
    """获取所有可用的服务商列表"""
    providers = {
        "deepseek": {
            "name": "DeepSeek 官方",
            "enabled": False
        },
        "aliyun": {
            "name": "阿里云/百炼",
            "enabled": True
        },
        "siliconflow_pro": {
            "name": "硅基流动Pro",
            "enabled": True
        },
        "siliconflow_normal": {
            "name": "硅基流动普通版",
            "enabled": True
        },
        "huoshan": {
            "name": "火山引擎",
            "enabled": True
        },
        "tencent": {
            "name": "腾讯云",
            "enabled": True
        }
    }
    return jsonify(providers)

@app.route('/test')
def run_test():
    selected_providers = request.args.getlist('providers[]')
    messages = [{'role': 'user', 'content': "给我写一首七言绝句，赞叹祖国的大好河山"}]
    
    def generate():
        # 在生成器函数内创建会话
        with app.app_context():
            # 创建新的测试会话
            session = TestSession(prompt=messages[0]['content'])
            db.session.add(session)
            db.session.commit()
            
            # 首先显示测试提示词
            prompt_message = f"测试提示词：{messages[0]['content']}\n\n"
            yield f"data: {json.dumps({'type': 'log', 'content': prompt_message})}\n\n"
            
            prefix_mapping = {
                "DeepSeek 官方": "DEEPSEEK",
                "阿里云/百炼": "ALIYUN",
                "硅基流动Pro": "SILICONFLOW",
                "硅基流动普通版": "SILICONFLOW",
                "火山引擎": "HUOSHAN",
                "腾讯云": "TENCENT"
            }
            
            for provider_name in selected_providers:
                if provider_name in prefix_mapping:
                    try:
                        prefix = prefix_mapping[provider_name]
                        config = get_provider_config(prefix, provider_name)
                        
                        for result in test_provider(config, messages):
                            if result["type"] == "log":
                                yield f"data: {json.dumps({'type': 'log', 'content': result['content']})}\n\n"
                            elif result["type"] == "result":
                                # 在每次数据库操作时重新获取会话
                                current_session = db.session.get(TestSession, session.id)
                                # 创建新的测试记录，关联到当前会话
                                record = TestRecord(
                                    session_id=current_session.id,
                                    provider=result["data"]["provider"],
                                    first_token_time=round(result["data"]["first_token_time"], 2) if result["data"]["first_token_time"] else None,
                                    reasoning_speed=round(result["data"]["reasoning_tokens"] / result["data"]["reasoning_time"], 2) if result["data"]["reasoning_time"] > 0 else 0,
                                    content_speed=round(result["data"]["content_tokens"] / result["data"]["content_time"], 2) if result["data"]["content_time"] > 0 else 0,
                                    average_speed=round(result["data"]["overall_tokens"] / result["data"]["total_time"], 2) if result["data"]["total_time"] > 0 else 0,
                                    log_content=result["data"]["log_content"]
                                )
                                db.session.add(record)
                                db.session.commit()
                                
                                result_data = {
                                    'type': 'result',
                                    'data': {
                                        'provider': record.provider,
                                        'first_token_time': record.first_token_time,
                                        'reasoning_speed': record.reasoning_speed,
                                        'content_speed': record.content_speed,
                                        'average_speed': record.average_speed,
                                    }
                                }
                                yield f"data: {json.dumps(result_data)}\n\n"
                    except Exception as e:
                        app.logger.error(f"测试 {provider_name} 时发生错误: {str(e)}")
                        # 在每次数据库操作时重新获取会话
                        current_session = db.session.get(TestSession, session.id)
                        # 记录错误信息
                        error_record = TestRecord(
                            session_id=current_session.id,
                            provider=provider_name,
                            error=str(e)
                        )
                        db.session.add(error_record)
                        db.session.commit()
                        yield f"data: {json.dumps({'type': 'error', 'provider': provider_name, 'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/history')
def get_history():
    # 获取所有测试会话及其关联的记录
    sessions = TestSession.query.order_by(TestSession.test_time.desc()).all()
    return jsonify([{
        "id": session.id,
        "test_time": session.test_time.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'),
        "prompt": session.prompt,
        "records": [{
            "provider": record.provider,
            "first_token_time": record.first_token_time,
            "reasoning_speed": record.reasoning_speed,
            "content_speed": record.content_speed,
            "average_speed": record.average_speed,
            "error": record.error
        } for record in session.records]
    } for session in sessions])

@app.route('/history/<int:session_id>', methods=['DELETE'])
def delete_history(session_id):
    try:
        # 使用 db.session.get() 替代 TestSession.query.get()
        session = db.session.get(TestSession, session_id)
        if session is None:
            return jsonify({'success': False, 'message': '记录不存在'}), 404
            
        # 删除关联的测试记录
        TestRecord.query.filter_by(session_id=session_id).delete()
        
        # 删除会话
        db.session.delete(session)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"删除历史记录时发生错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True) 