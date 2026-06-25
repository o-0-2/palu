import requests
from bs4 import BeautifulSoup
import re
import json
import os
import time
from urllib.parse import urljoin

# ---------- 1. 健壮的帕鲁页面解析器 ----------
def parse_pal_page_robust(html_content):
    """从 HTML 中提取帕鲁的文本数据，兼容性更好"""
    soup = BeautifulSoup(html_content, 'html.parser')
    data = {}

    # ---------- 名称 ----------
    title_tag = soup.find('title')
    if title_tag:
        title_text = title_tag.text.strip()
        data['name'] = title_text.split(' - ')[0] if ' - ' in title_text else title_text
    else:
        h1 = soup.find('h1')
        data['name'] = h1.text.strip() if h1 else None

    # ---------- 编号 ----------
    og_title = soup.find('meta', {'property': 'og:title'})
    if og_title and og_title.get('content'):
        match = re.search(r'No\.(\d+)', og_title['content'])
        if match:
            data['number'] = match.group(1)
        else:
            data['number'] = None
    if not data.get('number'):
        text = soup.get_text()
        match = re.search(r'[#＃](\d{3})', text)
        data['number'] = match.group(1) if match else None

    # ---------- 属性 ----------
    if og_title and og_title.get('content'):
        match = re.search(r'No\.\d+\s+(\S+)属性', og_title['content'])
        if match:
            data['type'] = match.group(1)
        else:
            data['type'] = None
    else:
        # 在页面中查找属性关键词
        type_keywords = ['无属性', '火属性', '水属性', '草属性', '雷属性',
                         '冰属性', '龙属性', '暗属性', '地属性']
        for elem in soup.find_all(['div', 'span']):
            text = elem.text.strip()
            if text in type_keywords:
                data['type'] = text
                break
        else:
            data['type'] = None

    # ---------- 稀有度 ----------
    text = soup.get_text()
    match = re.search(r'稀有度[：:]\s*(\d+)', text)
    data['rarity'] = match.group(1) if match else None

    # ---------- 描述 ----------
    # 查找引号内的典型描述
    match = re.search(r'"([^"]*?(?:它只要走在坡道上|幻兽帕鲁)[^"]*?)"', text, re.DOTALL)
    if match:
        data['description'] = ' '.join(match.group(1).split())
    else:
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            desc = meta_desc['content']
            quote_match = re.search(r'"([^"]*?)"', desc)
            if quote_match:
                data['description'] = quote_match.group(1)
            else:
                data['description'] = desc[:150] + '...' if len(desc) > 150 else desc
        else:
            data['description'] = None

    # ---------- 伙伴技能 ----------
    partner_data = {}
    for h3 in soup.find_all('h3'):
        if '伙伴技能' in h3.text:
            parent = h3.find_parent('div')
            if parent:
                name_elem = parent.find('h4')
                desc_elem = parent.find('p', class_=re.compile(r'text-gray'))
                if name_elem:
                    partner_data['name'] = name_elem.text.strip()
                if desc_elem:
                    partner_data['description'] = desc_elem.text.strip()
                if not partner_data:
                    div_text = parent.get_text()
                    match = re.search(r'([^。]*?)[。，,]\s*(.*?)(?=发动后|$)', div_text, re.DOTALL)
                    if match:
                        partner_data['name'] = match.group(1).strip()
                        partner_data['description'] = match.group(2).strip()
            break
    data['partner_skill'] = partner_data if partner_data else None

    # ---------- 工作适应性 ----------
    work_items = []
    for h3 in soup.find_all('h3'):
        if '工作适应性' in h3.text:
            parent = h3.find_parent('div')
            if parent:
                for item in parent.find_all('div', class_=re.compile(r'flex items-center gap-3')):
                    name_elem = item.find('div', class_=re.compile(r'text-gray'))
                    level_elem = item.find('div', class_=re.compile(r'text-blue'))
                    if name_elem:
                        name = name_elem.text.strip()
                        level = None
                        if level_elem:
                            level_match = re.search(r'(\d+)', level_elem.text)
                            if level_match:
                                level = int(level_match.group(1))
                        if name:
                            work_items.append({'name': name, 'level': level})
            break
    data['work_suitability'] = work_items

    # ---------- 进食量 ----------
    food_amount = 0
    for h3 in soup.find_all('h3'):
        if '进食量' in h3.text:
            parent = h3.find_parent('div')
            if parent:
                # 亮着的食物图标有绿色阴影
                on_icons = parent.find_all('div', class_=re.compile(r'drop-shadow.*green'))
                food_amount = len(on_icons)
            break
    data['food_amount'] = food_amount if food_amount > 0 else None

    # ---------- 基础属性 ----------
    base_stats = {}
    for h3 in soup.find_all('h3'):
        if '基础属性' in h3.text:
            parent = h3.find_parent('div')
            if parent:
                for row in parent.find_all('div', class_=re.compile(r'flex justify-between')):
                    label = row.find('span', class_=re.compile(r'text-gray'))
                    value = row.find('span', class_=re.compile(r'text-white'))
                    if label and value:
                        try:
                            base_stats[label.text.strip()] = int(value.text.strip())
                        except ValueError:
                            pass
            break
    data['base_stats'] = base_stats

    # ---------- 移动能力 ----------
    move_stats = {}
    for h3 in soup.find_all('h3'):
        if '移动能力' in h3.text:
            parent = h3.find_parent('div')
            if parent:
                for row in parent.find_all('div', class_=re.compile(r'flex justify-between')):
                    label = row.find('span', class_=re.compile(r'text-gray'))
                    value = row.find('span', class_=re.compile(r'text-white'))
                    if label and value:
                        try:
                            move_stats[label.text.strip()] = int(value.text.strip())
                        except ValueError:
                            pass
            break
    data['move_stats'] = move_stats

    # ---------- 等级65属性范围 ----------
    range_stats = {}
    for h3 in soup.find_all('h3'):
        if '等级' in h3.text and '属性范围' in h3.text:
            parent = h3.find_parent('div')
            if parent:
                for row in parent.find_all('div', class_=re.compile(r'flex justify-between')):
                    label = row.find('span', class_=re.compile(r'text-gray'))
                    value = row.find('span', class_=re.compile(r'text-white'))
                    if label and value:
                        nums = re.findall(r'\d+', value.text)
                        if len(nums) >= 2:
                            range_stats[label.text.strip()] = (int(nums[0]), int(nums[1]))
            break
    data['range_stats'] = range_stats if range_stats else None

    # ---------- 主动技能 ----------
    skills = []
    for h3 in soup.find_all('h3'):
        if '主动技能' in h3.text:
            parent = h3.find_parent('div')
            if parent:
                for card in parent.find_all('a', class_=re.compile(r'bg-\[\#222\]')):
                    skill = {}
                    name_elem = card.find('h4')
                    if name_elem:
                        skill['name'] = name_elem.text.strip()
                    type_elem = card.find('div', class_=re.compile(r'h-6.*element'))
                    if type_elem:
                        skill['type'] = type_elem.text.strip()
                    level_elem = card.find('div', string=re.compile(r'Lv\.'))
                    if level_elem:
                        match = re.search(r'(\d+)', level_elem.text)
                        if match:
                            skill['level'] = int(match.group(1))
                    power_elem = card.find('div', class_=re.compile(r'text-orange'))
                    if power_elem:
                        match = re.search(r'(\d+)', power_elem.text)
                        if match:
                            skill['power'] = int(match.group(1))
                    cd_elem = card.find('div', string=re.compile(r'冷却'))
                    if cd_elem:
                        match = re.search(r'(\d+)', cd_elem.text)
                        if match:
                            skill['cooldown'] = int(match.group(1))
                    desc_elem = card.find('p', class_=re.compile(r'text-gray'))
                    if desc_elem:
                        skill['description'] = desc_elem.text.strip()
                    if skill.get('name'):
                        skills.append(skill)
            break
    data['active_skills'] = skills

    # ---------- 掉落物品 ----------
    drops = []
    for h3 in soup.find_all('h3'):
        if '掉落物品' in h3.text:
            parent = h3.find_parent('div')
            if parent:
                for row in parent.find_all('tr', class_=re.compile(r'border-b')):
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        name_elem = cells[0].find('span', class_=re.compile(r'text-white'))
                        if name_elem:
                            drops.append({
                                'name': name_elem.text.strip(),
                                'quantity': cells[1].text.strip() if len(cells) > 1 else None,
                                'probability': cells[2].text.strip() if len(cells) > 2 else None
                            })
            break
    data['drops'] = drops

    # ---------- 团队/部族 ----------
    tribes = []
    for h3 in soup.find_all('h3'):
        if '团队/部族' in h3.text:
            parent = h3.find_parent('div')
            if parent:
                for link in parent.find_all('a', class_='block'):
                    name_span = link.find('span', class_=re.compile(r'text-red'))
                    if name_span:
                        tribes.append({
                            'name': name_span.text.strip(),
                            'url': link.get('href')
                        })
            break
    data['tribes'] = tribes

    # ---------- 出现地点 ----------
    locations = []
    for h3 in soup.find_all('h3'):
        if '出现地点' in h3.text:
            parent = h3.find_parent('div')
            if parent:
                for item in parent.find_all('div', class_=re.compile(r'flex justify-between')):
                    name_elem = item.find('span', class_=re.compile(r'text-gray'))
                    level_elem = item.find('div', class_=re.compile(r'inline-flex'))
                    if name_elem:
                        loc = {'name': name_elem.text.strip()}
                        if level_elem:
                            nums = re.findall(r'\d+', level_elem.text)
                            if len(nums) >= 2:
                                loc['level_min'] = int(nums[0])
                                loc['level_max'] = int(nums[1])
                        locations.append(loc)
            break
    data['locations'] = locations

    return data


# ---------- 2. 构建帕鲁索引 ----------
def build_pal_index(cache_file='pal_index.json'):
    """从列表页获取所有帕鲁的 {name, number, slug} 列表并缓存"""
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass

    print("正在从列表页构建帕鲁索引...")
    url = 'https://paldb.cn/pals'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    pals = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('/pals/') and href != '/pals/':
            slug = href.replace('/pals/', '').strip('/')
            # 尝试从 img 的 alt 获取名称
            img = a.find('img')
            if img and img.get('alt'):
                name = img['alt'].strip()
            else:
                # 否则从文本中提取
                name_span = a.find('span', class_=re.compile(r'name'))
                if name_span:
                    name = name_span.text.strip()
                else:
                    name = slug  # 后备

            # 提取编号
            number = None
            text = a.text
            match = re.search(r'No\.(\d+)', text)
            if match:
                number = match.group(1)
            pals.append({
                'name': name,
                'number': number,
                'slug': slug
            })

    # 去重
    seen = set()
    unique = []
    for p in pals:
        if p['slug'] not in seen:
            seen.add(p['slug'])
            unique.append(p)

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print(f"索引构建完成，共 {len(unique)} 个帕鲁")
    return unique


# ---------- 3. 搜索匹配 ----------
def search_pal(keyword, index):
    """根据关键词搜索，返回匹配列表"""
    keyword = keyword.strip().lower()
    matches = []
    for p in index:
        if keyword in p['name'].lower():
            matches.append(p)
        elif p['number'] and keyword == p['number']:
            matches.append(p)
        elif keyword in p['slug'].lower():
            matches.append(p)
    return matches


# ---------- 4. 获取单个帕鲁详情 ----------
def fetch_pal_detail(slug):
    url = f'https://paldb.cn/pals/{slug}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return parse_pal_page_robust(resp.text)


# ---------- 5. 主交互程序 ----------
def main():
    # 构建或加载索引
    index = build_pal_index()

    while True:
        keyword = input("\n请输入帕鲁名称、编号或Slug（输入 'q' 退出）：").strip()
        if keyword.lower() == 'q':
            break
        if not keyword:
            continue

        results = search_pal(keyword, index)
        if not results:
            print("未找到匹配的帕鲁，请重新输入。")
            continue

        # 多结果选择
        if len(results) > 1:
            print(f"找到 {len(results)} 个匹配项：")
            for i, p in enumerate(results, 1):
                print(f"{i}. {p['name']} (编号: {p['number'] or '未知'}, slug: {p['slug']})")
            choice = input("请选择序号（直接回车选择第一个）：").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(results):
                selected = results[int(choice)-1]
            else:
                selected = results[0]
        else:
            selected = results[0]
            print(f"找到帕鲁：{selected['name']} (编号: {selected['number'] or '未知'})")

        # 获取详情
        try:
            detail = fetch_pal_detail(selected['slug'])
            # 添加 slug 字段便于标识
            detail['slug'] = selected['slug']
            print("\n" + json.dumps(detail, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"获取详情失败：{e}")


if __name__ == '__main__':
    main()