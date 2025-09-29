import time
import sys
from bs4 import BeautifulSoup
import winsound
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import urllib.parse
from datetime import datetime, timedelta
import os
import tempfile
import urllib.request

try:
    from tkcalendar import DateEntry
except ImportError:
    DateEntry = None



class TrainWatcherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Отслеживание билетов на поезда')
        self.geometry('900x800')
        self.resizable(False, False)
        self.configure(bg='#f5f6fa')
        self.html_path = tk.StringVar(value='')
        self.trains = []
        self.vars = []
        self.checkboxes = []
        self.watching = False
        self.beep_thread = None
        self.watch_thread = None
        self.create_widgets()
    def _bind_entry_shortcuts(self, entry: tk.Entry):
        # Copy / Cut / Paste (Ctrl и Command)
        entry.bind('<Control-c>',  lambda e: e.widget.event_generate('<<Copy>>'))
        entry.bind('<Control-C>',  lambda e: e.widget.event_generate('<<Copy>>'))
        entry.bind('<Control-x>',  lambda e: e.widget.event_generate('<<Cut>>'))
        entry.bind('<Control-X>',  lambda e: e.widget.event_generate('<<Cut>>'))
        entry.bind('<Control-v>',  lambda e: e.widget.event_generate('<<Paste>>'))
        entry.bind('<Control-V>',  lambda e: e.widget.event_generate('<<Paste>>'))
        # macOS Command key equivalents
        entry.bind('<Command-c>', lambda e: e.widget.event_generate('<<Copy>>'))
        entry.bind('<Command-v>', lambda e: e.widget.event_generate('<<Paste>>'))
        entry.bind('<Command-x>', lambda e: e.widget.event_generate('<<Cut>>'))
        # Select All (Ctrl/Command + A)
        def _select_all(event):
            event.widget.select_range(0, 'end')
            event.widget.icursor('end')
            return 'break'
        entry.bind('<Control-a>', _select_all)
        entry.bind('<Control-A>', _select_all)
        entry.bind('<Command-a>', _select_all)
        entry.bind('<Command-A>', _select_all)
    def create_widgets(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', font=('Segoe UI', 12), padding=6)
        style.configure('TLabel', font=('Segoe UI', 11), background='#f5f6fa')
        style.configure('Train.TFrame', background='#ffffff', relief='groove', borderwidth=1)
        style.configure('Train.TLabel', font=('Segoe UI', 10), background='#ffffff')
        style.configure('Status.TLabel', font=('Segoe UI', 12, 'bold'), background='#f5f6fa', foreground='#2d3436')

        # --- Форма выбора направления и даты ---
        route_frame = ttk.Frame(self, style='Train.TFrame')
        route_frame.pack(fill='x', padx=10, pady=(10, 0))
        ttk.Label(route_frame, text='Маршрут:', style='TLabel').pack(side='left', padx=(0, 10))
        self.route_var = tk.StringVar(value='mg')
        route_combo = ttk.Combobox(route_frame, textvariable=self.route_var, state='readonly', width=18, font=('Segoe UI', 11))
        route_combo['values'] = ['Минск — Гомель', 'Гомель — Минск']
        route_combo.current(0)
        route_combo.pack(side='left', padx=(0, 10))
        ttk.Label(route_frame, text='Дата:', style='TLabel').pack(side='left', padx=(10, 10))
        if DateEntry:
            self.date_var = tk.StringVar()
            self.date_entry = DateEntry(route_frame, textvariable=self.date_var, width=12, font=('Segoe UI', 11), date_pattern='yyyy-mm-dd', locale='ru_RU')
            self.date_entry.set_date((datetime.now() + timedelta(days=1)))
            self.date_entry.pack(side='left', padx=(0, 10))
        else:
            self.date_var = tk.StringVar(value=(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'))
            self.date_entry = ttk.Entry(route_frame, textvariable=self.date_var, width=12, font=('Segoe UI', 11))
            self.date_entry.pack(side='left', padx=(0, 10))
            messagebox.showerror('Ошибка', 'Для календаря установите пакет tkcalendar:\n pip install tkcalendar')
        self.gen_link_btn = ttk.Button(route_frame, text='Сформировать ссылку', command=self.generate_link)
        self.gen_link_btn.pack(side='left', padx=(10, 0))

        # Ввод ссылки/пути к файлу
        link_frame = ttk.Frame(self, style='Train.TFrame')
        link_frame.pack(fill='x', padx=10, pady=(15, 0))
        ttk.Label(link_frame, text='Путь к HTML-файлу или ссылка:', style='TLabel').pack(side='left', padx=(0, 10))
        self.link_entry = ttk.Entry(link_frame, textvariable=self.html_path, width=70, font=('Segoe UI', 11))
        self.link_entry.pack(side='left', padx=(0, 10))

        title = ttk.Label(self, text='Выберите поезда для отслеживания билетов:', font=('Segoe UI', 16, 'bold'), background='#f5f6fa')
        title.pack(pady=(20, 10))

        # Основная область с поездами
        self.main_frame = ttk.Frame(self, style='Train.TFrame')
        self.main_frame.pack(fill='both', expand=True, padx=10, pady=(0, 0))

        self.canvas = tk.Canvas(self.main_frame, borderwidth=0, background='#f5f6fa', highlightthickness=0, width=880, height=500)
        self.frame = ttk.Frame(self.canvas, style='Train.TFrame')
        self.vsb = ttk.Scrollbar(self.main_frame, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side='right', fill='y', padx=(0, 0), pady=(0, 0))
        self.canvas.pack(side='left', fill='both', expand=True, padx=(0, 0))
        self.canvas.create_window((0, 0), window=self.frame, anchor='nw')

        # Прокрутка колесиком мыши
        self.canvas.bind('<Enter>', lambda e: self._bind_mousewheel())
        self.canvas.bind('<Leave>', lambda e: self._unbind_mousewheel())

        self.populate_trains()

        self.frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox('all'))

        # Нижний фрейм для кнопок и статуса
        bottom_frame = ttk.Frame(self, style='Train.TFrame')
        bottom_frame.pack(fill='x', padx=10, pady=(0, 20), side='bottom')

        self.status = ttk.Label(bottom_frame, text='Ожидание выбора поездов...', style='Status.TLabel')
        self.status.pack(side='left', padx=(0, 20), pady=10)

        self.start_btn = ttk.Button(bottom_frame, text='Начать отслеживание', command=self.start_watching)
        self.start_btn.pack(side='right', pady=10, padx=(0, 10))

        self.stop_btn = ttk.Button(bottom_frame, text='Остановить', command=self.stop_watching, state='disabled')
        self.stop_btn.pack(side='right', pady=10, padx=(0, 10))

        # Временная кнопка для теста звука
        self.test_sound_btn = ttk.Button(bottom_frame, text='Тест звука', command=self.test_sound)
        self.test_sound_btn.pack(side='right', pady=10, padx=(0, 10))
        self._bind_entry_shortcuts(self.link_entry)
        
     
    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1*(event.delta/120)), 'units')
        elif event.num == 4:
            self.canvas.yview_scroll(-1, 'units')
        elif event.num == 5:
            self.canvas.yview_scroll(1, 'units')

    def _bind_mousewheel(self):
        self.canvas.bind_all('<MouseWheel>', self._on_mousewheel)
        self.canvas.bind_all('<Button-4>', self._on_mousewheel)
        self.canvas.bind_all('<Button-5>', self._on_mousewheel)

    def _unbind_mousewheel(self):
        self.canvas.unbind_all('<MouseWheel>')
        self.canvas.unbind_all('<Button-4>')
        self.canvas.unbind_all('<Button-5>')

    def populate_trains(self):
        for widget in self.frame.winfo_children():
            widget.destroy()
        self.vars.clear()
        self.checkboxes.clear()
        columns = 2
        for idx, t in enumerate(self.trains, 1):
            var = tk.BooleanVar()
            self.vars.append(var)
            train_frame = ttk.Frame(self.frame, style='Train.TFrame')
            row = (idx - 1) // columns
            col = (idx - 1) % columns
            train_frame.grid(row=row, column=col, sticky='nwes', pady=4, padx=4)
            cb = tk.Checkbutton(train_frame, variable=var, bg='#ffffff')
            cb.grid(row=0, column=0, rowspan=2, padx=(4, 10), pady=4)
            self.checkboxes.append(cb)
            info = f"[{idx}] Поезд {t['number']} ({t['route_type']})\nМаршрут: {t['route']}\nОтправление: {t['dep_time']} ({t['dep_station']})\nПрибытие: {t['arr_time']} ({t['arr_station']})\nВ пути: {t['duration']}\nБилеты в продаже: {'Да' if t['ticket_allowed'] else 'Нет'}"
            label = ttk.Label(train_frame, text=info, style='Train.TLabel', justify='left')
            label.grid(row=0, column=1, sticky='w', padx=4, pady=4)
            cars = '\n'.join([f"    {car['type']}: {car['places']} мест, {car['price']} {car['currency']}" for car in t['cars']])
            label2 = ttk.Label(train_frame, text=cars, style='Train.TLabel', justify='left', foreground='#636e72')
            label2.grid(row=1, column=1, sticky='w', padx=4, pady=(0, 4))
        for col in range(columns):
            self.frame.grid_columnconfigure(col, weight=1)

    def generate_link(self):
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='disabled')
        self.status.config(text='Генерация ссылки...')
        self.vars.clear()
        self.checkboxes.clear()
        for widget in self.frame.winfo_children():
            widget.destroy()
        self.frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox('all'))
        self.update()
        route = self.route_var.get()
        date = self.date_var.get().strip()
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
        except Exception:
            messagebox.showerror('Ошибка', 'Дата должна быть в формате ГГГГ-ММ-ДД!')
            self.start_btn.config(state='normal')
            return
        if route == 'Минск — Гомель' or route == 'mg':
            from_station = 'Минск-Пассажирский'
            from_exp = '2100001'
            from_esr = '140210'
            to_station = 'Гомель'
            to_exp = '2100100'
            to_esr = '150000'
        else:
            from_station = 'Гомель'
            from_exp = '2100100'
            from_esr = '150000'
            to_station = 'Минск-Пассажирский'
            to_exp = '2100001'
            to_esr = '140210'
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        if date == datetime.now().strftime('%Y-%m-%d'):
            front_date = 'сегодня'
        elif date == tomorrow:
            front_date = 'завтра'
        else:
            front_date = date
        url = (
            'https://pass.rw.by/ru/route/?'
            f'from={urllib.parse.quote(from_station)}'
            f'&from_exp={from_exp}'
            f'&from_esr={from_esr}'
            f'&to={urllib.parse.quote(to_station)}'
            f'&to_exp={to_exp}'
            f'&to_esr={to_esr}'
            f'&front_date={urllib.parse.quote(front_date)}'
            f'&date={date}'
        )
        self.html_path.set(url)
        self.status.config(text='Ссылка сгенерирована! Загрузка...')
        threading.Thread(target=self.reload_trains, daemon=True).start()

    def reload_trains(self):
        path = self.html_path.get().strip()
        if not path:
            self.after(0, lambda: messagebox.showwarning('Внимание', 'Укажите путь к HTML-файлу или ссылку!'))
            return
        self.after(0, lambda: self.status.config(text='Загрузка...'))
        self.update()
        if path.startswith('http://') or path.startswith('https://'):
            try:
                tmp_fd, tmp_path = tempfile.mkstemp(suffix='.html')
                os.close(tmp_fd)
                urllib.request.urlretrieve(path, tmp_path)
                trains_path = tmp_path
            except Exception as e:
                self.after(0, lambda: messagebox.showerror('Ошибка', f'Не удалось скачать страницу:\n{e}'))
                self.after(0, lambda: self.start_btn.config(state='normal'))
                return
        else:
            trains_path = path
        try:
            trains = parse_trains_from_path(trains_path)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror('Ошибка', f'Не удалось загрузить файл:\n{e}'))
            self.after(0, lambda: self.start_btn.config(state='normal'))
            return
        def update_ui():
            self.trains = trains
            self.populate_trains()
            self.frame.update_idletasks()
            self.canvas.config(scrollregion=self.canvas.bbox('all'))
            self.status.config(text='Данные обновлены. Ожидание выбора поездов...')
            self.start_btn.config(state='normal')
        self.after(0, update_ui)
        if path.startswith('http://') or path.startswith('https://'):
            try:
                os.remove(trains_path)
            except Exception:
                pass

    def start_watching(self):
        selected = [i for i, v in enumerate(self.vars) if v.get()]
        if not selected:
            messagebox.showwarning('Внимание', 'Выберите хотя бы один поезд!')
            return
        self.status.config(text='Отслеживание...')
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.watching = True
        self.watch_thread = threading.Thread(target=self.watch_loop, args=(selected,), daemon=True)
        self.watch_thread.start()

    def stop_watching(self):
        self.watching = False
        self.status.config(text='Отслеживание остановлено.')
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')

    def watch_loop(self, selected):
        while self.watching:
            path = self.html_path.get().strip()
            if path.startswith('http://') or path.startswith('https://'):
                try:
                    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.html')
                    os.close(tmp_fd)
                    urllib.request.urlretrieve(path, tmp_path)
                    trains_path = tmp_path
                except Exception as e:
                    self.after(0, lambda: self.status.config(text=f'Ошибка скачивания: {e}'))
                    self.watching = False
                    self.after(0, lambda: self.start_btn.config(state='normal'))
                    self.after(0, lambda: self.stop_btn.config(state='disabled'))
                    return
            else:
                trains_path = path
            try:
                trains = parse_trains_from_path(trains_path)
            except Exception as e:
                self.after(0, lambda: self.status.config(text=f'Ошибка загрузки: {e}'))
                self.watching = False
                self.after(0, lambda: self.start_btn.config(state='normal'))
                self.after(0, lambda: self.stop_btn.config(state='disabled'))
                return
            if path.startswith('http://') or path.startswith('https://'):
                try:
                    os.remove(trains_path)
                except Exception:
                    pass
            for idx in selected:
                t = trains[idx]
                if t['ticket_allowed']:
                    self.after(0, lambda: self.status.config(text=f'Билеты появились на поезд [{idx+1}] {t["number"]}!'))
                    def show_info():
                        self._beep_active = True
                        self.beep_thread = threading.Thread(target=self.beep_until_close, daemon=True)
                        self.beep_thread.start()
                        messagebox.showinfo('Билеты найдены!', f'Билеты появились на поезд [{idx+1}] {t["number"]}!\n\nНажмите OK, чтобы остановить писк.')
                        self.stop_beep()
                        self.watching = False
                        self.status.config(text='Ожидание выбора поездов...')
                        self.start_btn.config(state='normal')
                        self.stop_btn.config(state='disabled')
                    self.after(0, show_info)
                    return
            self.after(0, lambda: self.status.config(text=f'{time.strftime("%H:%M:%S")}: Билетов пока нет. Следующая проверка через 20 секунд...'))
            time.sleep(20)

    def beep_until_close(self):
        self._beep_active = True
        def beep_loop():
            while self._beep_active:
                winsound.Beep(1000, 500)  
        t = threading.Thread(target=beep_loop, daemon=True)
        t.start()
        t.join()

    def stop_beep(self):
        self._beep_active = False

    def test_sound(self):
        def show_test():
            self._beep_active = True
            self.beep_thread = threading.Thread(target=self.beep_until_close, daemon=True)
            self.beep_thread.start()
            messagebox.showinfo('Тест звука', 'Это тестовый сигнал!\n\nНажмите OK, чтобы остановить писк.')
            self.stop_beep()
        threading.Thread(target=show_test, daemon=True).start()

def parse_trains_from_path(path):
    with open(path, encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'lxml')
    trains = []
    for row_wrap in soup.select('.sch-table__row-wrap'):
        row = row_wrap.select_one('.sch-table__row')
        if not row:
            continue
        train_number = row.get('data-train-number', '').strip()
        train_type = row.get('data-train-type', '').strip()
        ticket_allowed = row.get('data-ticket_selling_allowed', '') == 'true'
        route_type = row.select_one('.sch-table__route-type')
        route_type = route_type.text.strip() if route_type else ''
        route = row.select_one('.sch-table__route .train-route')
        route = route.text.strip() if route else ''
        dep_time = row.select_one('.train-from-time')
        dep_time = dep_time.text.strip() if dep_time else ''
        dep_station = row.select_one('.train-from-name')
        dep_station = dep_station.text.strip() if dep_station else ''
        arr_time = row.select_one('.train-to-time')
        arr_time = arr_time.text.strip() if arr_time else ''
        arr_station = row.select_one('.train-to-name')
        arr_station = arr_station.text.strip() if arr_station else ''
        duration = row.select_one('.train-duration-time')
        duration = duration.text.strip() if duration else ''
        car_types = []
        for t_item in row.select('.sch-table__t-item'):
            car_name = t_item.select_one('.sch-table__t-name')
            car_name = car_name.text.strip() if car_name else ''
            quant = t_item.select_one('.sch-table__t-quant span')
            quant = quant.text.strip() if quant else ''
            price = t_item.select_one('.ticket-cost')
            price = price.text.strip() if price else ''
            currency = t_item.select_one('.ticket-currency')
            currency = currency.text.strip() if currency else ''
            if car_name or price:
                car_types.append({
                    'type': car_name,
                    'places': quant,
                    'price': price,
                    'currency': currency
                })
        trains.append({
            'number': train_number,
            'type': train_type,
            'route_type': route_type,
            'route': route,
            'dep_time': dep_time,
            'dep_station': dep_station,
            'arr_time': arr_time,
            'arr_station': arr_station,
            'duration': duration,
            'ticket_allowed': ticket_allowed,
            'cars': car_types
        })
    return trains

if __name__ == '__main__':
    app = TrainWatcherApp()
    app.mainloop()
